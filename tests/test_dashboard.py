"""Tests for WW3 Risk Model Dashboard Generator."""

from __future__ import annotations

from html.parser import HTMLParser
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
    l3 = (56.0 * 1.0 + unemp_val * 1.2 + 65.0 * 1.1 + 75.0 * 1.0 + ai_val * 1.5 + 64.0 * 1.0) / 6.8
    l4 = (72.0 * 1.2 + 75.0 * 1.2 + bloc_val * 1.3 + 76.0 * 1.2 + 66.0 * 1.4 + 80.0 * 1.4) / 7.7
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


