"""Comprehensive tests for WW3 Risk Model.

Required coverage:
(a) Normalization / boundary 0-100
(b) Monotonicity: Unemployment or AI displacement rising -> total risk does not fall
(c) Gate: Peace mechanism improving -> total risk falls
(d) Interaction effect exists: Simultaneously pushing L1+L2 yields larger increase than the sum of pushing each individually (superadditivity)
(e) Historical ranking: 1938 risk > 1913 risk, and 1962 is high (>= 70)
Additional coverage:
- Scenario loading & schema validation
- Scenario relative rankings (detente < baseline < shocks)
- Probability bands logic
- Four-stage classification
- Markdown report generation
- CLI invocation
"""

import json
from pathlib import Path
import pytest

from ww3_risk.indicators import (
    Indicator,
    LayerData,
    GateBuffer,
    ScenarioData,
    load_scenario_from_file,
)
from ww3_risk.model import WW3RiskModel, StageInfo, RiskResult
from ww3_risk.scenarios import apply_shocks, compare_scenarios
from ww3_risk.report import generate_markdown_report
from ww3_risk.cli import main as cli_main


BASE_DIR = Path(__file__).resolve().parent.parent
BASELINE_FILE = BASE_DIR / "scenarios" / "baseline_2026.json"
HISTORICAL_FILE = BASE_DIR / "data" / "historical_cases.json"
SCENARIOS_DIR = BASE_DIR / "scenarios"


@pytest.fixture
def baseline_scenario() -> ScenarioData:
    return load_scenario_from_file(BASELINE_FILE)


@pytest.fixture
def historical_scenarios() -> list[ScenarioData]:
    with open(HISTORICAL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [ScenarioData.from_dict(d) for d in data]


@pytest.fixture
def model() -> WW3RiskModel:
    return WW3RiskModel()


# ==============================================================================
# (a) Normalization / Boundary tests (0 - 100)
# ==============================================================================

def test_boundary_zero_and_hundred(model: WW3RiskModel):
    """Test boundary conditions: all zeros should yield 0 risk; all 100s with collapsed peace should cap at 100."""
    # Scenario: All zeros (zero structural pressure, perfect peace)
    zero_layers = {
        f"L{i}": LayerData(
            id=f"L{i}",
            name=f"Layer {i}",
            name_en=f"Layer {i}",
            indicators=[Indicator(id=f"i_{i}", name="ind", name_en="ind", value=0.0)]
        )
        for i in range(1, 6)
    }
    zero_buffers = [
        GateBuffer(id="b1", name="buf", name_en="buf", value=100.0)
    ]
    scenario_zero = ScenarioData(
        id="zero",
        title="Zero Risk",
        title_en="Zero Risk",
        description="Zero scenario",
        layers=zero_layers,
        gate_buffers=zero_buffers,
    )
    result_zero = model.evaluate(scenario_zero)
    assert result_zero.global_risk_index == 0.0
    assert result_zero.base_structural_score == 0.0
    assert result_zero.stage.stage_number == 1

    # Scenario: Extreme 100s (max pressure, zero peace)
    max_layers = {
        f"L{i}": LayerData(
            id=f"L{i}",
            name=f"Layer {i}",
            name_en=f"Layer {i}",
            indicators=[Indicator(id=f"i_{i}", name="ind", name_en="ind", value=100.0)]
        )
        for i in range(1, 6)
    }
    max_buffers = [
        GateBuffer(id="b1", name="buf", name_en="buf", value=0.0)
    ]
    scenario_max = ScenarioData(
        id="max",
        title="Max Risk",
        title_en="Max Risk",
        description="Max scenario",
        layers=max_layers,
        gate_buffers=max_buffers,
    )
    result_max = model.evaluate(scenario_max)
    assert 99.0 <= result_max.global_risk_index <= 100.0
    assert result_max.stage.stage_number == 4


def test_indicator_validation_bounds():
    """Indicator and GateBuffer must reject out-of-bound values (<0 or >100)."""
    with pytest.raises(ValueError):
        Indicator(id="test", name="t", name_en="t", value=-0.1)

    with pytest.raises(ValueError):
        Indicator(id="test", name="t", name_en="t", value=100.1)

    with pytest.raises(ValueError):
        GateBuffer(id="test", name="t", name_en="t", value=-1.0)

    with pytest.raises(ValueError):
        GateBuffer(id="test", name="t", name_en="t", value=105.0)


# ==============================================================================
# (b) Monotonicity: Unemployment or AI displacement rising -> total risk does not fall
# ==============================================================================

def test_monotonicity_ai_displacement(baseline_scenario: ScenarioData, model: WW3RiskModel):
    """Monotonicity: Increasing AI displacement rate strictly increases or maintains total risk."""
    res_base = model.evaluate(baseline_scenario)

    shock_mid = apply_shocks(
        baseline_scenario,
        indicator_overrides={"l3_ai_displacement_rate": 80.0},
    )
    res_mid = model.evaluate(shock_mid)

    shock_high = apply_shocks(
        baseline_scenario,
        indicator_overrides={"l3_ai_displacement_rate": 98.0},
    )
    res_high = model.evaluate(shock_high)

    assert res_mid.global_risk_index >= res_base.global_risk_index
    assert res_high.global_risk_index >= res_mid.global_risk_index
    assert res_high.global_risk_index > res_base.global_risk_index


def test_monotonicity_youth_unemployment(baseline_scenario: ScenarioData, model: WW3RiskModel):
    """Monotonicity: Increasing youth unemployment strictly increases total risk."""
    res_base = model.evaluate(baseline_scenario)

    shock_up = apply_shocks(
        baseline_scenario,
        indicator_overrides={"l3_youth_unemployment": 95.0},
    )
    res_up = model.evaluate(shock_up)

    assert res_up.global_risk_index > res_base.global_risk_index


# ==============================================================================
# (c) Gate: Peace mechanism improving -> total risk falls
# ==============================================================================

def test_gate_peace_mechanism_improving_reduces_risk(baseline_scenario: ScenarioData, model: WW3RiskModel):
    """Gate test: Strengthening peace buffers strictly lowers global risk score."""
    res_base = model.evaluate(baseline_scenario)

    # Enhance diplomatic trust and trade interdependence
    enhanced_peace = apply_shocks(
        baseline_scenario,
        buffer_overrides={
            "gate_diplomatic_trust": 85.0,
            "gate_trade_interdependence": 85.0,
            "gate_international_institutions": 80.0,
            "gate_nuclear_deterrence_stability": 90.0,
        },
    )
    res_peace = model.evaluate(enhanced_peace)

    assert res_peace.peace_capacity > res_base.peace_capacity
    assert res_peace.gate_factor < res_base.gate_factor
    assert res_peace.global_risk_index < res_base.global_risk_index


def test_gate_peace_mechanism_collapse_increases_risk(baseline_scenario: ScenarioData, model: WW3RiskModel):
    """Gate test: Collapsing peace buffers strictly magnifies global risk score."""
    res_base = model.evaluate(baseline_scenario)

    collapsed_peace = apply_shocks(
        baseline_scenario,
        buffer_overrides={
            "gate_diplomatic_trust": 10.0,
            "gate_trade_interdependence": 10.0,
            "gate_international_institutions": 10.0,
            "gate_nuclear_deterrence_stability": 20.0,
        },
    )
    res_collapsed = model.evaluate(collapsed_peace)

    assert res_collapsed.peace_capacity < res_base.peace_capacity
    assert res_collapsed.gate_factor > res_base.gate_factor
    assert res_collapsed.global_risk_index > res_base.global_risk_index


# ==============================================================================
# (d) Interaction effect: Superadditivity (L1 + L2 simultaneous > sum of individual)
# ==============================================================================

def test_interaction_superadditivity_l1_l2(model: WW3RiskModel):
    """Interaction test: Pushing L1 and L2 simultaneously yields a larger increase than the sum of pushing each individually."""
    # Construct a neutral baseline with mid-range scores (50 each) and neutral gate (50 capacity -> gate factor 1.0)
    layers = {
        f"L{i}": LayerData(
            id=f"L{i}",
            name=f"Layer {i}",
            name_en=f"Layer {i}",
            indicators=[Indicator(id=f"ind_{i}", name="ind", name_en="ind", value=50.0)]
        )
        for i in range(1, 6)
    }
    buffers = [
        GateBuffer(id="b1", name="buf", name_en="buf", value=50.0)
    ]
    base_scenario = ScenarioData(
        id="neutral_base",
        title="Neutral",
        title_en="Neutral",
        description="Neutral",
        layers=layers,
        gate_buffers=buffers,
    )
    r_base = model.evaluate(base_scenario)

    delta = 20.0

    # 1. Shock only L1
    sc_l1 = apply_shocks(base_scenario, indicator_overrides={"ind_1": 50.0 + delta})
    r_l1 = model.evaluate(sc_l1)
    delta_r_l1 = r_l1.global_risk_index - r_base.global_risk_index

    # 2. Shock only L2
    sc_l2 = apply_shocks(base_scenario, indicator_overrides={"ind_2": 50.0 + delta})
    r_l2 = model.evaluate(sc_l2)
    delta_r_l2 = r_l2.global_risk_index - r_base.global_risk_index

    # 3. Shock both L1 and L2 simultaneously
    sc_both = apply_shocks(base_scenario, indicator_overrides={"ind_1": 50.0 + delta, "ind_2": 50.0 + delta})
    r_both = model.evaluate(sc_both)
    delta_r_both = r_both.global_risk_index - r_base.global_risk_index

    # Superadditivity check: delta_r_both must be strictly greater than (delta_r_l1 + delta_r_l2)
    diff = delta_r_both - (delta_r_l1 + delta_r_l2)
    assert diff > 0.05, f"Expected superadditivity, but diff was {diff}"


# ==============================================================================
# (e) Historical ranking: 1938 risk > 1913 risk, and 1962 is high (>= 70)
# ==============================================================================

def test_historical_cases_ranking(historical_scenarios: list[ScenarioData], model: WW3RiskModel):
    """Historical test: 1938 risk > 1913 risk, 1962 is high (>= 70), and 1990 is lowest."""
    results = {s.id: model.evaluate(s) for s in historical_scenarios}

    score_1938 = results["hist_1938"].global_risk_index
    score_1913 = results["hist_1913"].global_risk_index
    score_1962 = results["hist_1962"].global_risk_index
    score_1990 = results["hist_1990"].global_risk_index
    score_2025 = results["hist_2025"].global_risk_index

    # 1. 1938 > 1913
    assert score_1938 > score_1913, f"Expected 1938 ({score_1938}) > 1913 ({score_1913})"

    # 2. 1962 is high (near-miss Cuban missile crisis, >= 70)
    assert score_1962 >= 70.0, f"Expected 1962 to be high (>= 70.0), got {score_1962}"

    # 3. 1990 (Cold War peace dividend) is lowest and Stage 1
    assert score_1990 < score_1913
    assert score_1990 < score_1962
    assert score_1990 < score_2025
    assert results["hist_1990"].stage.stage_number == 1

    # 4. 1938 is highest (Stage 4)
    assert score_1938 > score_1962
    assert results["hist_1938"].stage.stage_number == 4


# ==============================================================================
# Scenario comparisons and rankings
# ==============================================================================

def test_scenario_relative_rankings(model: WW3RiskModel):
    """detente must be lowest; baseline_2026 must be intermediate; AI shock and energy crisis higher than baseline."""
    baseline = load_scenario_from_file(SCENARIOS_DIR / "baseline_2026.json")
    ai_shock = load_scenario_from_file(SCENARIOS_DIR / "ai_displacement_shock.json")
    energy_shock = load_scenario_from_file(SCENARIOS_DIR / "energy_food_crisis.json")
    detente = load_scenario_from_file(SCENARIOS_DIR / "detente.json")

    r_base = model.evaluate(baseline)
    r_ai = model.evaluate(ai_shock)
    r_energy = model.evaluate(energy_shock)
    r_detente = model.evaluate(detente)

    assert r_detente.global_risk_index < r_base.global_risk_index, (
        f"Detente ({r_detente.global_risk_index}) should be lower than baseline ({r_base.global_risk_index})"
    )
    assert r_ai.global_risk_index > r_base.global_risk_index, (
        f"AI Shock ({r_ai.global_risk_index}) should be higher than baseline ({r_base.global_risk_index})"
    )
    assert r_energy.global_risk_index > r_base.global_risk_index, (
        f"Energy Crisis ({r_energy.global_risk_index}) should be higher than baseline ({r_base.global_risk_index})"
    )


# ==============================================================================
# Probability bands and stage mapping
# ==============================================================================

def test_probability_bands_order(baseline_scenario: ScenarioData, model: WW3RiskModel):
    """Probability bands: 10y central > 5y central > 1y central."""
    res = model.evaluate(baseline_scenario)
    p1 = res.probability_bands["1y"].central_pct
    p5 = res.probability_bands["5y"].central_pct
    p10 = res.probability_bands["10y"].central_pct

    assert p1 < p5 < p10
    assert 0.0 <= p1 <= 100.0
    assert 0.0 <= res.probability_bands["1y"].lower_pct <= res.probability_bands["1y"].upper_pct <= 100.0


def test_probability_bands_anchor_table_calibration(model: WW3RiskModel):
    """Anchor table calibration test (v0.2):
    Verify that 1y, 5y, 10y central probabilities at index 25, 50, 75, 85, 100
    fall strictly within the required tolerance (+-3% for 25-85, +-5% for 100).
    """
    anchors = [
        # (index, target_1y, target_5y, target_10y, tolerance)
        (25.0, 0.5, 2.0, 5.0, 3.0),
        (50.0, 2.0, 8.0, 15.0, 3.0),
        (75.0, 6.0, 22.0, 38.0, 3.0),
        (85.0, 10.0, 32.0, 50.0, 3.0),
        (100.0, 20.0, 55.0, 75.0, 5.0),
    ]

    for score, tgt_1y, tgt_5y, tgt_10y, tol in anchors:
        bands = model.calculate_probability_bands(score)
        p1 = bands["1y"].central_pct
        p5 = bands["5y"].central_pct
        p10 = bands["10y"].central_pct

        assert abs(p1 - tgt_1y) <= tol, f"Score {score} 1y: got {p1}%, target {tgt_1y}% (tol +-{tol}%)"
        assert abs(p5 - tgt_5y) <= tol, f"Score {score} 5y: got {p5}%, target {tgt_5y}% (tol +-{tol}%)"
        assert abs(p10 - tgt_10y) <= tol, f"Score {score} 10y: got {p10}%, target {tgt_10y}% (tol +-{tol}%)"

        # Horizon monotonicity: 1y < 5y < 10y
        assert p1 < p5 < p10

        # Asymptotic bounds: never 0% or 100%
        assert 0.0 < bands["1y"].lower_pct <= p1 <= bands["1y"].upper_pct < 100.0
        assert 0.0 < bands["5y"].lower_pct <= p5 <= bands["5y"].upper_pct < 100.0
        assert 0.0 < bands["10y"].lower_pct <= p10 <= bands["10y"].upper_pct < 100.0


def test_probability_bands_continuous_monotonicity(model: WW3RiskModel):
    """Verify strictly monotonic increasing behavior across 0 to 100 in steps of 1."""
    prev_1y = -1.0
    prev_5y = -1.0
    prev_10y = -1.0

    for s in range(0, 101):
        bands = model.calculate_probability_bands(float(s))
        c1 = bands["1y"].central_pct
        c5 = bands["5y"].central_pct
        c10 = bands["10y"].central_pct

        assert c1 > prev_1y, f"1y monotonicity violated at {s}: {c1} <= {prev_1y}"
        assert c5 > prev_5y, f"5y monotonicity violated at {s}: {c5} <= {prev_5y}"
        assert c10 > prev_10y, f"10y monotonicity violated at {s}: {c10} <= {prev_10y}"
        assert c1 < c5 < c10, f"Ordering violated at {s}: {c1}, {c5}, {c10}"

        prev_1y = c1
        prev_5y = c5
        prev_10y = c10


def test_stage_mapping_comprehensive(model: WW3RiskModel):
    assert model.map_stage(15.0).stage_number == 1
    assert model.map_stage(35.0).stage_number == 2
    assert model.map_stage(60.0).stage_number == 3
    assert model.map_stage(85.0).stage_number == 4


# ==============================================================================
# Markdown report and CLI tests
# ==============================================================================

def test_markdown_report_generation(baseline_scenario: ScenarioData, model: WW3RiskModel):
    res = model.evaluate(baseline_scenario)
    md = generate_markdown_report(res)

    assert "# WW3 結構風險評估報告" in md
    assert "戰爭風險指數 (War Risk Index)" in md
    assert "五層結構風險明細" in md
    assert "和平機制閘門分析" in md
    assert "系統互動加成效應" in md
    assert "結構風險情境帶" in md
    assert "免責聲明" in md


def test_cli_single_scenario(capsys):
    cli_main(["--scenario", str(BASELINE_FILE)])
    captured = capsys.readouterr()
    assert "戰爭風險指數" in captured.out
    assert "危機升級階段" in captured.out


def test_cli_data_quality_report(capsys):
    """Test P3 data quality CLI feature."""
    cli_main(["--data-quality", "--scenario", str(BASELINE_FILE)])
    captured = capsys.readouterr()
    assert "WW3 風險模型 - 數據品質與更新新鮮度報告" in captured.out
    assert "整體數據完整度 (Completeness)" in captured.out
    assert "[STALE]" in captured.out
    assert "[FRESH]" in captured.out
    assert "l1_food_security" in captured.out


def test_cli_data_quality_json(capsys):
    """Test P3 data quality CLI JSON output."""
    import json
    cli_main(["--data-quality", "--scenario", str(BASELINE_FILE), "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["total_indicators"] == 34
    assert data["completeness_pct"] == 100.0
    assert data["fresh_count"] >= 1
    assert data["missing_count"] == 0
    assert len(data["items"]) == 34


def test_indicator_staleness_and_missing_detection():
    """Verify that Indicator correctly evaluates fresh, stale, and missing statuses."""
    from ww3_risk.indicators import Indicator

    # 1. Fresh indicator
    ind_fresh = Indicator(
        id="test_fresh",
        name="Fresh Test",
        name_en="Fresh Test",
        value=50.0,
        raw_value=100,
        source="Test Source",
        publication_date="2026-10-01",
        stale_after="365d",
        normalization_method="Linear",
        evidence_level="verified",
    )
    assert ind_fresh.get_quality_status("2026-10-21") == "fresh"

    # 2. Stale indicator (published 2024 with 365d threshold)
    ind_stale = Indicator(
        id="test_stale",
        name="Stale Test",
        name_en="Stale Test",
        value=50.0,
        raw_value=100,
        source="Test Source",
        publication_date="2024-01-01",
        stale_after="365d",
        normalization_method="Linear",
        evidence_level="verified",
    )
    assert ind_stale.get_quality_status("2026-10-21") == "stale"

    # 3. Missing raw value
    ind_missing = Indicator(
        id="test_missing",
        name="Missing Test",
        name_en="Missing Test",
        value=50.0,
        raw_value="",
        source="Test Source",
        evidence_level="verified",
    )
    assert ind_missing.get_quality_status("2026-10-21") == "missing"


def test_cli_comparison_and_report(tmp_path, capsys):
    report_file = tmp_path / "test_report.md"
    cli_main([
        "--compare",
        str(SCENARIOS_DIR / "baseline_2026.json"),
        str(SCENARIOS_DIR / "detente.json"),
        "--report",
        str(report_file),
    ])
    captured = capsys.readouterr()
    assert "情境對比分析" in captured.out
    assert report_file.exists()
    assert len(report_file.read_text(encoding="utf-8")) > 100


def test_cli_historical(capsys):
    cli_main(["--historical", str(HISTORICAL_FILE)])
    captured = capsys.readouterr()
    assert "歷史案例結構風險排序" in captured.out
    assert "1938" in captured.out
    assert "1913" in captured.out


# ==============================================================================
# Additional rigorous tests
# ==============================================================================

def test_evidence_counts_breakdown(baseline_scenario: ScenarioData, model: WW3RiskModel):
    res = model.evaluate(baseline_scenario)
    # v0.3: 7 verified, 20 inference, 7 illustrative (total 34)
    assert res.evidence_counts["verified"] == 7
    assert res.evidence_counts["inference"] == 20
    assert res.evidence_counts["illustrative"] == 7
    assert res.evidence_counts["verified"] + res.evidence_counts["inference"] >= 25
    assert sum(res.evidence_counts.values()) == len(baseline_scenario.gate_buffers) + sum(
        len(layer.indicators) for layer in baseline_scenario.layers.values()
    )


def test_interaction_cap_enforcement(model: WW3RiskModel):
    """When raw interactions exceed max_interaction_cap, total must be capped."""
    res_inter = model.calculate_interactions(
        l1=100.0, l2=100.0, l3=100.0, l4=100.0, l5=100.0, gate_failure=100.0
    )
    assert res_inter["is_capped"] is True
    assert res_inter["total"] == model.max_interaction_cap


def test_gate_factor_exact_values(model: WW3RiskModel):
    """Test gate factor at 0%, 50%, and 100% peace capacity."""
    assert model.calculate_gate_factor(100.0) == pytest.approx(0.6, abs=1e-5)
    assert model.calculate_gate_factor(50.0) == pytest.approx(1.0, abs=1e-5)
    assert model.calculate_gate_factor(0.0) == pytest.approx(1.4, abs=1e-5)


def test_json_serialization(baseline_scenario: ScenarioData, model: WW3RiskModel):
    """RiskResult.to_dict() must be completely JSON-serializable."""
    res = model.evaluate(baseline_scenario)
    d = res.to_dict()
    json_str = json.dumps(d, ensure_ascii=False)
    loaded = json.loads(json_str)
    assert loaded["scenario_id"] == "baseline_2026"
    assert "global_risk_index" in loaded
    assert "probability_bands" in loaded


def test_immutability_of_base_scenario(baseline_scenario: ScenarioData):
    """apply_shocks should not mutate original ScenarioData."""
    orig_val = baseline_scenario.layers["L3"].get_indicator("l3_ai_displacement_rate").value
    new_scenario = apply_shocks(
        baseline_scenario,
        indicator_overrides={"l3_ai_displacement_rate": orig_val + 10.0},
    )
    after_val = baseline_scenario.layers["L3"].get_indicator("l3_ai_displacement_rate").value
    assert orig_val == after_val
    assert new_scenario.layers["L3"].get_indicator("l3_ai_displacement_rate").value == orig_val + 10.0


def test_cli_missing_file_exits(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["--scenario", "nonexistent_file_xyz.json"])
    assert excinfo.value.code == 1


# ==============================================================================
# P4 Verification Tests: Sensitivity, Gate Directionality, Extreme Boundaries
# ==============================================================================

def test_sensitivity_analysis_ranking_top_five(baseline_scenario: ScenarioData, model: WW3RiskModel):
    """P4: Test sensitivity across all indicators and verify top influential items."""
    import copy
    sc = copy.deepcopy(baseline_scenario)
    base_res = model.evaluate(sc)
    base_idx = base_res.global_risk_index

    impacts = {}

    # Measure layer indicators
    for lid, layer in sc.layers.items():
        for ind in layer.indicators:
            orig = ind.value
            ind.value = min(100.0, orig + 10.0)
            idx_p = model.evaluate(sc).global_risk_index
            ind.value = max(0.0, orig - 10.0)
            idx_m = model.evaluate(sc).global_risk_index
            ind.value = orig
            impacts[ind.id] = (abs(idx_p - base_idx) + abs(base_idx - idx_m)) / 2.0

    # Measure gate buffers
    for buf in sc.gate_buffers:
        orig = buf.value
        buf.value = min(100.0, orig + 10.0)
        idx_p = model.evaluate(sc).global_risk_index
        buf.value = max(0.0, orig - 10.0)
        idx_m = model.evaluate(sc).global_risk_index
        buf.value = orig
        impacts[buf.id] = (abs(idx_p - base_idx) + abs(base_idx - idx_m)) / 2.0

    sorted_impacts = sorted(impacts.items(), key=lambda x: x[1], reverse=True)
    top_5_ids = [item[0] for item in sorted_impacts[:5]]

    # All gate buffers are among the top most sensitive items due to gate multiplier effect
    assert "gate_nuclear_deterrence_stability" in top_5_ids
    assert "gate_diplomatic_trust" in top_5_ids
    assert "gate_trade_interdependence" in top_5_ids
    # Top structural layer indicator is AI displacement rate
    assert sorted_impacts[4][0] == "l3_ai_displacement_rate" or "gate_international_institutions" in top_5_ids


def test_gate_behavior_directionality(baseline_scenario: ScenarioData, model: WW3RiskModel):
    """P4: With all else equal, improving peace mechanism strictly reduces risk; failure strictly increases risk."""
    import copy
    sc = copy.deepcopy(baseline_scenario)
    base_risk = model.evaluate(sc).global_risk_index

    # 1. Peace buffers improve (+15 across all buffers)
    sc_improved = copy.deepcopy(sc)
    for buf in sc_improved.gate_buffers:
        buf.value = min(100.0, buf.value + 15.0)
    risk_improved = model.evaluate(sc_improved).global_risk_index
    assert risk_improved < base_risk, f"Improving peace buffers must reduce risk: {risk_improved} < {base_risk}"

    # 2. Peace buffers collapse (-15 across all buffers)
    sc_failed = copy.deepcopy(sc)
    for buf in sc_failed.gate_buffers:
        buf.value = max(0.0, buf.value - 15.0)
    risk_failed = model.evaluate(sc_failed).global_risk_index
    assert risk_failed > base_risk, f"Failing peace buffers must increase risk: {risk_failed} > {base_risk}"


def test_extreme_boundary_scenarios(baseline_scenario: ScenarioData, model: WW3RiskModel):
    """P4: Test boundary conditions: all zeros, all hundreds, single layer max. Outputs must stay in [0, 100] with no NaN."""
    import copy
    import math

    # 1. All zeros
    sc_zero = copy.deepcopy(baseline_scenario)
    for layer in sc_zero.layers.values():
        for ind in layer.indicators:
            ind.value = 0.0
    for buf in sc_zero.gate_buffers:
        buf.value = 100.0  # Perfect peace
    res_zero = model.evaluate(sc_zero)
    assert not math.isnan(res_zero.global_risk_index)
    assert 0.0 <= res_zero.global_risk_index <= 5.0

    # 2. All hundreds
    sc_hundred = copy.deepcopy(baseline_scenario)
    for layer in sc_hundred.layers.values():
        for ind in layer.indicators:
            ind.value = 100.0
    for buf in sc_hundred.gate_buffers:
        buf.value = 0.0  # Total gate collapse
    res_hundred = model.evaluate(sc_hundred)
    assert not math.isnan(res_hundred.global_risk_index)
    assert 95.0 <= res_hundred.global_risk_index <= 100.0

    # 3. Single layer max, others zero
    for lid in ["L1", "L2", "L3", "L4", "L5"]:
        sc_single = copy.deepcopy(baseline_scenario)
        for l in sc_single.layers.values():
            for ind in l.indicators:
                ind.value = 100.0 if l.id == lid else 0.0
        for buf in sc_single.gate_buffers:
            buf.value = 50.0
        res_single = model.evaluate(sc_single)
        assert not math.isnan(res_single.global_risk_index)
        assert 0.0 <= res_single.global_risk_index <= 100.0


def test_historical_backtest_discipline(model: WW3RiskModel):
    """P4: Verify historical backtest cases execute truthfully and respect discipline."""
    import json
    with open(HISTORICAL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    cases = data if isinstance(data, list) else data.get("cases", [])
    assert len(cases) >= 5

    results = {}
    for case in cases:
        sc = ScenarioData.from_dict(case)
        res = model.evaluate(sc)
        results[case["year"]] = res.global_risk_index
        assert 0.0 <= res.global_risk_index <= 100.0
        # Disclaimer must be present on all probability bands
        for b in res.probability_bands.values():
            assert "結構風險之情境推演估算" in b.disclaimer

    # Verify expected historical order without hindsight manipulation:
    # 1938 and 1913 are highest (Stage 4), 1990 is lowest (Stage 1)
    assert results[1938] > 95.0
    assert results[1913] > 90.0
    assert results[1990] < 35.0
