"""Tests for WW3 Risk Model Dashboard Generator."""

from __future__ import annotations

import json
import re
from pathlib import Path

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
    assert round(main_res["base_structural_score"], 1) == round(expected_result.base_structural_score, 1)
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

    # Regional pressures check
    assert len(data["regional_pressures"]) == 5
    for reg in data["regional_pressures"]:
        assert "score" in reg
        assert 0.0 <= reg["score"] <= 100.0
        assert "level" in reg
        assert "note" in reg
        assert "示意拆分" in reg["note"]

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
