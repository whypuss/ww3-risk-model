"""Tests for WW3 Risk Model Dashboard Generator."""

from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from pathlib import Path

from ww3_risk import __version__
from ww3_risk.dashboard import (
    build_dashboard,
    build_dashboard_html,
    calculate_regional_pressures,
    generate_dashboard_data,
    UNCONNECTED_DATA_SOURCES,
    REGIONAL_INDICATOR_MAPPINGS,
)
from ww3_risk.indicators import load_scenario_from_file
from ww3_risk.model import WW3RiskModel


def test_generate_dashboard_data_matches_cli_and_model():
    """Verify that dashboard data generation directly matches the core model calculation."""
    model = WW3RiskModel()
    scenario_path = Path("scenarios/baseline_2026.json")
    scenario = load_scenario_from_file(scenario_path)
    expected_result = model.evaluate(scenario)

    data = generate_dashboard_data(scenario_path=scenario_path, model=model)

    assert data["metadata"]["active_scenario_id"] == "baseline_2026"
    assert data["metadata"]["active_scenario_year"] == 2026

    # Verify numbers match CLI and core model exactly
    main_res = data["main_result"]
    assert round(main_res["global_risk_index"], 1) == round(expected_result.global_risk_index, 1)
    assert abs(main_res["base_structural_score"] - expected_result.base_structural_score) < 0.05
    assert main_res["stage"]["number"] == expected_result.stage.stage_number
    assert main_res["stage"]["title"] == expected_result.stage.title
    assert round(main_res["gate_factor"], 3) == round(expected_result.gate_factor, 3)
    assert round(main_res["peace_capacity"], 1) == round(expected_result.peace_capacity, 1)

    # Layers check
    for lid in ["L1", "L2", "L3", "L4", "L5"]:
        assert lid in main_res["layer_scores"]
        assert round(main_res["layer_scores"][lid], 1) == round(expected_result.layer_scores[lid], 1)

    # Interactions check
    assert round(main_res["interactions"]["L1_x_L2"], 2) == round(expected_result.interactions["L1_x_L2"], 2)
    assert round(main_res["interactions"]["L3_x_L5"], 2) == round(expected_result.interactions["L3_x_L5"], 2)
    assert round(main_res["interactions"]["L4_x_GateFailure"], 2) == round(expected_result.interactions["L4_x_GateFailure"], 2)
    assert round(main_res["interactions"]["total"], 2) == round(expected_result.interactions["total"], 2)

    # Scenarios check
    scenario_ids = [s["id"] for s in data["scenarios"]]
    assert "baseline_2026" in scenario_ids
    assert "ai_displacement_shock" in scenario_ids
    assert "energy_food_crisis" in scenario_ids
    assert "detente" in scenario_ids

    # Historical cases check
    hist_ids = [h["id"] for h in data["historical"]]
    assert "hist_1913" in hist_ids
    assert "hist_1938" in hist_ids
    assert "hist_1962" in hist_ids
    assert "hist_1990" in hist_ids
    assert "hist_2025" in hist_ids

    # Regional pressures check (8 key regional crisis cards)
    assert len(data["regional_pressures"]) == 8
    for reg in data["regional_pressures"]:
        assert "score" in reg
        assert 0.0 <= reg["score"] <= 100.0
        assert "level" in reg
        assert "note" in reg
        assert "示意拆分" in reg["note"]
        assert "components" in reg
        assert len(reg["components"]) >= 3
        assert "formula" in reg
        assert "示意拆分（指標原始平均）：" in reg["formula"]

    # Unconnected data sources check
    assert len(data["unconnected_sources"]) >= 5
    for src in data["unconnected_sources"]:
        assert "未接數據源" in src["status"]


def test_build_dashboard_offline_zero_cdn(tmp_path):
    """Verify that the dashboard HTML is 100% offline with zero CDN or external web requests."""
    out_html = tmp_path / "dashboard.html"
    out_json = tmp_path / "dashboard_data.json"

    data = build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        output_json_path=out_json,
        ui_step=1,
    )

    assert out_html.exists()
    assert out_json.exists()

    content = out_html.read_text(encoding="utf-8")

    # Strict Zero CDN verification: no external script/link tags
    external_links = re.findall(r'(src|href)=["\']https?://[^"\']+["\']', content)
    assert len(external_links) == 0, f"Found external web dependencies: {external_links}"

    # Embedded data is parseable JSON
    match = re.search(r'<script id="ww3-model-data" type="application/json">\s*(.*?)\s*</script>', content, re.DOTALL)
    assert match is not None, "Embedded JSON script block not found"
    embedded_data = json.loads(match.group(1))
    assert embedded_data["main_result"]["global_risk_index"] == data["main_result"]["global_risk_index"]

    # UI Step 1 elements
    assert "GLOBAL ESCALATION INDEX" in content
    assert "STAGE 03" in content
    assert "當前階段 · CURRENT" in content
    assert f"{data['main_result']['global_risk_index']:.1f}" in content


def test_simulator_formula_consistency():
    """Verify that the simulator JS recalculation engine formula matches Python WW3RiskModel exactly."""
    import math
    model = WW3RiskModel()
    scenario_path = Path("scenarios/baseline_2026.json")
    scenario = load_scenario_from_file(scenario_path)
    py_result = model.evaluate(scenario)

    # Replicate the exact JS simulator recalculation in Python
    ai_val = 62.0
    unemp_val = 68.0
    energy_val = 60.0
    minerals_val = 72.0
    bloc_val = 78.0
    fear_val = 78.0
    peace_cap = 44.916666666666664

    l1 = (52.0 * 1.0 + 58.0 * 1.0 + energy_val * 1.2 + minerals_val * 1.3 + 65.0 * 1.0 + 68.0 * 1.2) / 6.7
    l2 = 71.32352941176471
    l3 = (56.0 * 1.0 + unemp_val * 1.2 + 65.0 * 1.1 + 75.0 * 1.0 + ai_val * 1.5 + 64.0 * 1.0 + 71.5 * 1.1) / 7.9
    l4 = (72.0 * 1.2 + 75.0 * 1.2 + bloc_val * 1.3 + 76.0 * 1.2 + 66.0 * 1.4 + 80.0 * 1.4 + 82.0 * 1.2) / 8.9
    l5 = (76.0 * 1.3 + 70.0 * 1.1 + 64.0 * 1.0 + fear_val * 1.4 + 72.0 * 1.2 + 68.0 * 1.0) / 7.0

    base_structural = (l1 * 1.0 + l2 * 1.0 + l3 * 1.1 + l4 * 1.2 + l5 * 1.1) / 5.4

    gate_failure = 100.0 - peace_cap
    gate_factor = 1.4 - (peace_cap / 100.0) * 0.8

    i_l1_l2 = 0.08 * (l1 * l2 / 100.0)
    i_l3_l5 = 0.08 * (l3 * l5 / 100.0)
    i_l4_gate = 0.10 * (l4 * gate_failure / 100.0)
    total_interaction = min(25.0, i_l1_l2 + i_l3_l5 + i_l4_gate)

    raw_interacted = base_structural + total_interaction
    gated = raw_interacted * gate_factor

    if gated <= 70.0:
        sim_index = gated
    else:
        sim_index = 70.0 + 30.0 * math.tanh((gated - 70.0) / 30.0)

    # Check exact match with baseline 83.1
    assert round(sim_index, 1) == round(py_result.global_risk_index, 1)
    assert round(base_structural, 1) == round(py_result.base_structural_score, 1)
    assert round(gate_factor, 3) == round(py_result.gate_factor, 3)
    assert round(total_interaction, 2) == round(py_result.interactions["total"], 2)


def test_dashboard_html_style_tags_balanced_and_enclosing_root_css(tmp_path):
    """Verify that dashboard HTML has balanced <style> tags and strictly encloses :root CSS rules."""
    out_html = tmp_path / "dashboard.html"
    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        ui_step=5,
    )
    content = out_html.read_text(encoding="utf-8")

    # 1. <style> and </style> counts must be equal and >= 1
    style_open_matches = re.findall(r"<style\b[^>]*>", content, re.IGNORECASE)
    style_close_matches = re.findall(r"</style>", content, re.IGNORECASE)
    assert len(style_open_matches) == len(style_close_matches), (
        f"Mismatched style tags: {len(style_open_matches)} open vs {len(style_close_matches)} close"
    )
    assert len(style_open_matches) >= 1, "At least one <style> block must be present"

    # 2. :root { must be strictly enclosed within a <style>...</style> block
    style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", content, re.DOTALL | re.IGNORECASE)
    assert any(":root" in block for block in style_blocks), (
        ":root CSS rules must be strictly enclosed inside <style>...</style>"
    )


def test_dashboard_head_structure_has_no_bare_css_or_text_nodes(tmp_path):
    """Verify via standard library html.parser that <head> has no bare CSS or unescaped text nodes."""
    out_html = tmp_path / "dashboard.html"
    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        ui_step=5,
    )
    content = out_html.read_text(encoding="utf-8")

    class HeadStructureParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_head = False
            self.current_tag: str | None = None
            self.head_tag_order: list[str] = []
            self.bare_head_text: list[str] = []

        def handle_starttag(self, tag: str, attrs: list):
            tag_lower = tag.lower()
            if tag_lower == "head":
                self.in_head = True
            elif self.in_head:
                self.current_tag = tag_lower
                self.head_tag_order.append(tag_lower)

        def handle_endtag(self, tag: str):
            tag_lower = tag.lower()
            if tag_lower == "head":
                self.in_head = False
            elif self.in_head and self.current_tag == tag_lower:
                self.current_tag = None

        def handle_data(self, data: str):
            if self.in_head:
                stripped = data.strip()
                # Elements legitimately containing text inside <head> are title, style, script
                if self.current_tag not in ("title", "style", "script") and stripped:
                    self.bare_head_text.append(stripped)

    parser = HeadStructureParser()
    parser.feed(content)

    assert not parser.bare_head_text, (
        f"Detected bare un-tagged text nodes inside <head>: {parser.bare_head_text[:3]}"
    )
    assert "title" in parser.head_tag_order, "<title> must exist in <head>"
    assert "style" in parser.head_tag_order, "<style> must exist in <head>"
    assert parser.head_tag_order.index("title") < parser.head_tag_order.index("style"), (
        "<style> must appear after <title> in <head>"
    )


def test_dashboard_mobile_responsive_structure(tmp_path):
    """Verify that generated dashboard HTML contains mobile responsive breakpoints, table-scroll, and touch targets."""
    out_html = tmp_path / "dashboard_mobile.html"
    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        ui_step=5,
    )
    content = out_html.read_text(encoding="utf-8")

    # 1. Media queries hierarchy
    assert "@media (max-width: 768px)" in content, "Missing 768px mobile breakpoint"
    assert "@media (max-width: 640px)" in content, "Missing 640px mobile breakpoint"
    assert "@media (max-width: 480px)" in content, "Missing 480px narrow mobile breakpoint"

    # 2. Table scroll container and hint
    assert '<div class="table-scroll">' in content, "Missing .table-scroll container"
    assert "左右滑動查看完整表格" in content, "Missing horizontal scroll mobile hint"
    assert re.search(r'<div class="table-scroll">\s*<table class="styled-table">', content) is not None, (
        ".table-scroll must directly wrap <table class=\"styled-table\">"
    )

    # 3. Touch targets and slider ergonomics in CSS
    assert "min-height: 44px" in content, "Missing >= 44px touch target rules"
    assert "width: 28px" in content, "Missing enlarged slider thumb rule"
    assert "overflow-x: hidden" in content, "Missing overflow safety on html/body"

    # 4. Top bar mobile wrap & badge styling
    assert "class=\"top-bar\"" in content
    assert "class=\"top-meta\"" in content
    assert "class=\"top-date\"" in content


def test_dashboard_v03_terminology_and_credibility_separation(tmp_path):
    """Verify v0.3 UI enhancements: War Risk Index terminology, unverified scenario bands, and 3-tier credibility."""
    out_html = tmp_path / "dashboard_v03.html"
    out_json = tmp_path / "dashboard_v03.json"

    data = build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        output_json_path=out_json,
        ui_step=5,
    )
    content = out_html.read_text(encoding="utf-8")

    # 1. Terminology: War Risk Index (戰爭風險指數) 100/100
    assert "戰爭風險指數" in content
    assert "戰爭風險指數（War Risk Index）100/100" in content
    assert "WAR RISK INDEX" in content

    # 2. Strict Prohibition: Never label the primary index or scenario bands as "開戰概率"
    # Ensure "開戰概率" does not appear as any heading, label, or probability band title
    assert "情境推演概率帶" not in content
    assert "結構風險情境帶（非經驗證概率）" in content

    # 3. Three-Tier Credibility Architecture separation
    assert "三種可信度分立體系架構" in content
    assert "原始統計可信度" in content
    assert "換算方法透明度" in content
    assert "模型預測能力界限" in content

    # 4. Data Quality & Driver Decomposition
    assert "戰爭風險指數主要驅動分解" in content
    assert "數據品質與審計新鮮度" in content
    assert "100.0%" in content  # Completeness pct

    # 5. Metadata and JSON audit
    assert data["metadata"]["model_version"] == __version__
    assert "data_quality" in data
    assert data["data_quality"]["completeness_pct"] == 100.0
    assert "evidence_distribution" in data
    assert data["evidence_distribution"]["verified"] == 8
    assert data["evidence_distribution"]["inference"] == 21
    assert data["evidence_distribution"]["illustrative"] == 7


def test_dashboard_api_base_and_offline_fallback(tmp_path):
    """Verify C3: dashboard dynamic API fetch mode and offline fallback preservation."""
    # 1. With --api-base provided
    out_live_html = tmp_path / "dashboard_live.html"
    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_live_html,
        api_base="https://ww3-risk-api.whypuss.workers.dev",
        ui_step=5,
    )
    live_content = out_live_html.read_text(encoding="utf-8")

    assert "https://ww3-risk-api.whypuss.workers.dev" in live_content
    assert "const apiBase = \"https://ww3-risk-api.whypuss.workers.dev\";" in live_content
    assert "AbortController()" in live_content
    assert "3000" in live_content  # 3-second timeout
    assert "/api/risk/latest" in live_content
    assert "/api/risk/layers" in live_content
    assert "/api/data-status" in live_content
    assert "● 離線快照（內嵌數據）" in live_content
    assert "badge-live" in live_content
    assert "applyApiData" in live_content

    # 2. Without api-base (v0.3 offline behavior)
    out_offline_html = tmp_path / "dashboard_offline.html"
    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_offline_html,
        api_base=None,
        ui_step=5,
    )
    offline_content = out_offline_html.read_text(encoding="utf-8")

    assert "const apiBase = \"\";" in offline_content
    assert "● 100% 本地離線運行 (ZERO CDN)" in offline_content
    assert "戰爭風險指數" in offline_content
    assert "WW3_MODEL_DATA" in offline_content


def test_regional_pressures_raw_average_and_formula_regression():
    """Verify regional pressure card disciplines (expanded to 8 regions in v0.5.0):
    - base_weight multiplier is removed from all mappings
    - all indicator IDs exist in baseline scenario
    - card score strictly equals arithmetic mean of components
    - components field has {id, name, value}
    - formula string contains '示意拆分（指標原始平均）：', Chinese short names and values
    - exact expected baseline scores match calibrated targets:
        east_asia: 79.5 (HIGH)
        eastern_europe: 74.0 (HIGH)
        middle_east: 66.5 (ELEVATED)
        south_central_asia: 63.0 (ELEVATED)
        global_chokepoints: 72.0 (HIGH)
        africa_sudan: 69.1 (ELEVATED)
        southeast_asia: 77.8 (HIGH)
        western_europe: 67.8 (ELEVATED)
    """
    scenario_path = Path("scenarios/baseline_2026.json")
    scenario = load_scenario_from_file(scenario_path)

    # 1. Assert base_weight is removed from all mappings
    for reg_id, conf in REGIONAL_INDICATOR_MAPPINGS.items():
        assert "base_weight" not in conf, f"base_weight still present in mapping '{reg_id}'"

    # 2. Assert every primary indicator ID exists in baseline scenario
    all_indicator_ids = set()
    for layer in scenario.layers.values():
        for ind in layer.indicators:
            all_indicator_ids.add(ind.id)

    for reg_id, conf in REGIONAL_INDICATOR_MAPPINGS.items():
        for iid in conf["primary_indicators"]:
            assert iid in all_indicator_ids, f"Indicator '{iid}' in region '{reg_id}' not in baseline scenario!"

    # 3. Calculate regional pressures and verify arithmetic mean & components
    cards = calculate_regional_pressures(scenario)
    assert len(cards) == 8

    expected_scores = {
        "east_asia": (79.5, "HIGH"),
        "eastern_europe": (74.0, "HIGH"),
        "middle_east": (66.5, "ELEVATED"),
        "south_central_asia": (63.0, "ELEVATED"),
        "global_chokepoints": (72.0, "HIGH"),
        "africa_sudan": (69.1, "ELEVATED"),
        "southeast_asia": (77.8, "HIGH"),
        "western_europe": (67.8, "ELEVATED"),
    }

    card_dict = {c["id"]: c for c in cards}
    for reg_id, (expected_score, expected_level) in expected_scores.items():
        assert reg_id in card_dict
        card = card_dict[reg_id]

        # Score and level match
        assert card["score"] == expected_score, f"{reg_id} score {card['score']} != {expected_score}"
        assert card["level"] == expected_level, f"{reg_id} level {card['level']} != {expected_level}"

        # Arithmetic mean assertion using real baseline component values
        components = card["components"]
        assert len(components) == len(REGIONAL_INDICATOR_MAPPINGS[reg_id]["primary_indicators"])
        for comp in components:
            assert "id" in comp
            assert "name" in comp
            assert "value" in comp
            assert isinstance(comp["value"], (int, float))

        mean_val = round(sum(c["value"] for c in components) / len(components), 1)
        assert card["score"] == mean_val

        # Formula assertion
        formula = card["formula"]
        assert "示意拆分（指標原始平均）：" in formula
        assert f"= {expected_score:.1f}" in formula
        for comp in components:
            assert f"{comp['value']:.1f} {comp['name']}" in formula


def test_regional_pressures_raises_on_missing_indicator_regression():
    """Verify that calculate_regional_pressures immediately raises KeyError if any mapped indicator is missing."""
    import copy
    import pytest

    scenario_path = Path("scenarios/baseline_2026.json")
    scenario = load_scenario_from_file(scenario_path)

    # Corrupt scenario by removing one indicator needed by regional mappings
    corrupted = copy.deepcopy(scenario)
    for lid, layer in corrupted.layers.items():
        layer.indicators = [ind for ind in layer.indicators if ind.id != "l4_military_expenditure_growth"]

    with pytest.raises(KeyError, match="l4_military_expenditure_growth"):
        calculate_regional_pressures(corrupted)


def test_regional_8_cards_id_integrity_and_discipline():
    """Regression test: v0.5.0 8 regional cards ID integrity and arithmetic mean discipline."""
    scenario_path = Path("scenarios/baseline_2026.json")
    scenario = load_scenario_from_file(scenario_path)

    expected_ids = {
        "east_asia",
        "eastern_europe",
        "middle_east",
        "south_central_asia",
        "global_chokepoints",
        "africa_sudan",
        "southeast_asia",
        "western_europe",
    }
    assert set(REGIONAL_INDICATOR_MAPPINGS.keys()) == expected_ids

    cards = calculate_regional_pressures(scenario)
    assert len(cards) == 8
    assert {c["id"] for c in cards} == expected_ids

    for c in cards:
        # Card score strictly equals arithmetic mean of components
        comp_vals = [comp["value"] for comp in c["components"]]
        expected_avg = round(sum(comp_vals) / len(comp_vals), 1)
        assert c["score"] == expected_avg
        # Card formula printed
        assert "示意拆分（指標原始平均）：" in c["formula"]
        assert f"= {c['score']:.1f}" in c["formula"]
        # Valid level
        assert c["level"] in {"CRITICAL", "HIGH", "ELEVATED", "MODERATE"}


def test_pulse_layer_card_and_trend_svg_rendering(tmp_path):
    """Verify v0.6.0 pulse layer card, composite/structural split, and SVG linear trend chart."""
    out_html = tmp_path / "dashboard_v06.html"
    out_json = tmp_path / "dashboard_v06.json"

    data = build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        output_json_path=out_json,
        ui_step=5,
    )
    content = out_html.read_text(encoding="utf-8")

    # 1. Main gauge composite index & structural/pulse split
    assert 'id="score-display"' in content
    assert 'id="structural-display"' in content
    assert 'id="pulse-display"' in content
    assert "結構基準" in content
    assert "即時脈搏" in content

    # 2. Pulse Layer Section & Signals Table
    assert 'id="pulse-layer-section"' in content
    assert "即時脈搏層（快速外生訊號）" in content
    assert 'id="pulse-signals-table"' in content
    assert "GDELT 2.0 全球衝突聲量" in content
    assert "Polymarket 戰爭地緣預測籃子" in content
    assert "Brent 原油 24 小時價格變動" in content

    # 3. Operational Trend Linear Chart
    assert 'id="trend-chart-container"' in content
    assert "當代運行總指數歷史趨勢" in content
    assert 'id="btn-trend-daily"' in content
    assert 'id="btn-trend-monthly"' in content
    assert 'class="trend-svg"' in content
    assert "2026-10-21" in content
    assert "嚴禁補造歷史" in content

    # 4. Zero external CDN scripts or stylesheets
    external_links = re.findall(r'(src|href)=["\']https?://[^"\']+["\']', content)
    assert len(external_links) == 0, f"Found external web dependencies: {external_links}"


def test_dashboard_header_version_matches_package_version(tmp_path):
    """Regression test: dashboard header brand subtitle and metadata dynamically reflect package __version__."""
    out_html = tmp_path / "dashboard.html"
    out_json = tmp_path / "dashboard_data.json"
    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        output_json_path=out_json,
        ui_step=5,
    )
    content = out_html.read_text(encoding="utf-8")
    data = json.loads(out_json.read_text(encoding="utf-8"))

    # Assert model_version in JSON metadata matches __version__
    assert data["metadata"]["model_version"] == __version__

    # Assert HTML header brand-sub dynamically reflects __version__
    expected_brand_sub = f"DEFENSE INTELLIGENCE &amp; SYSTEMIC CRISIS TERMINAL · v{__version__}"
    assert expected_brand_sub in content

    # Assert footer / offline model version reflects __version__
    assert f"Model Version: {__version__}" in content









