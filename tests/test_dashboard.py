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
    render_trend_svg,
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


def test_dashboard_no_simulator_section(tmp_path):
    """Verify that the Interactive Crisis Escalation Simulator section has been removed from the dashboard."""
    out_html = tmp_path / "dashboard.html"
    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        ui_step=5,
    )
    content = out_html.read_text(encoding="utf-8")

    # 1. Simulator section title must NOT be present
    assert "實時交互衝突模擬器" not in content
    assert "Interactive Crisis Escalation Simulator" not in content

    # 2. Simulator DOM elements (id="sim-") must NOT be present
    assert 'id="simulator-section"' not in content
    assert 'id="sim_l3_ai"' not in content
    assert 'id="sim_l3_unemp"' not in content
    assert 'id="sim_l1_energy"' not in content
    assert 'id="sim_l1_minerals"' not in content
    assert 'id="sim_l4_bloc"' not in content
    assert 'id="sim_l5_fear"' not in content
    assert 'id="sim_gate_peace"' not in content
    assert 'id="sim-index-display"' not in content
    assert 'id="sim-delta-display"' not in content
    assert 'id="sim-stage-display"' not in content
    assert 'id="sim-base-display"' not in content
    assert 'id="sim-gate-display"' not in content
    assert 'id="sim-inter-display"' not in content
    assert 'id="sim-raw-display"' not in content
    assert 'id="sim-prob-1y"' not in content
    assert 'id="sim-prob-5y"' not in content
    assert 'id="sim-prob-10y"' not in content

    # 3. Simulator CSS classes must NOT be present
    assert "simulator-layout" not in content
    assert "sim-controls-col" not in content
    assert "sim-result-col" not in content
    assert "sim-slider-group" not in content
    assert "sim-range" not in content
    assert "sim-result-card" not in content
    assert "sim-score-row" not in content
    assert "sim-metrics-grid" not in content
    assert "sim-prob-rows" not in content
    assert "sim-formula-note" not in content

    # 4. Simulator JS functions must NOT be present
    assert "function runSimulation()" not in content
    assert "function resetSimulation()" not in content

    # 5. Other dashboard sections must still be present
    assert "全球抗議活動監測" in content
    assert "歷史趨勢與重大危機回測對照" in content
    assert "情境卡矩陣與動態比對" in content
    assert "全球關鍵地緣戰區壓力卡列" in content
    assert "數據品質與審計新鮮度" in content
    assert "即時脈搏層" in content


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

    # 3. Touch targets in CSS
    assert "min-height: 44px" in content, "Missing >= 44px touch target rules"
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


def test_protests_snapshot_json_schema_and_data_discipline():
    """Verify v0.7.0 data/protests_snapshot.json is valid JSON, contains all required fields,
    and strictly adheres to data discipline (no percentage fields in themes, no 60+ decorative numbers).
    """
    protests_file = Path("data/protests_snapshot.json")
    assert protests_file.exists(), "data/protests_snapshot.json must exist"

    raw_text = protests_file.read_text(encoding="utf-8")
    protests = json.loads(raw_text)

    # Required top-level fields
    required_keys = {
        "as_of",
        "note",
        "weekly_events",
        "hotspots",
        "scale_bars",
        "themes",
        "timeline",
        "countries",
        "key_observations",
    }
    assert required_keys.issubset(protests.keys())
    assert protests["as_of"] == "2026-10-23"
    assert protests["note"] == "人工整理快照（非即時數據）"

    # Weekly events
    assert protests["weekly_events"]["value"] == 1072
    assert "Delta Watchfloor" in protests["weekly_events"]["source"]
    assert "含各種規模集會" in protests["weekly_events"]["caveat"]

    # Hotspots (5 countries)
    assert len(protests["hotspots"]) == 5
    hotspot_names = [h.get("name_zh") or h.get("country") for h in protests["hotspots"]]
    assert hotspot_names == ["法國", "意大利", "比利時", "葡萄牙", "西班牙"]

    # Scale bars (3 items: France, Serbia, Italy)
    assert len(protests["scale_bars"]) == 3
    fr_bar = protests["scale_bars"][0]
    assert fr_bar["min"] == 55 and fr_bar["max"] == 80
    assert fr_bar["label"] == "55–80 萬（官方 55／主辦方 80）"

    # Themes: strictly qualitative strings, no percentage fields or '%' symbols
    themes = protests["themes"]
    assert themes == ["生活成本", "房屋問題", "教育經費", "青年就業", "貪腐問責"]
    for item in themes:
        assert isinstance(item, str), "Each theme must be a plain qualitative string without percentage fields"
        assert "%" not in item and "％" not in item

    # Timeline (4 stations)
    assert len(protests["timeline"]) == 4

    # Countries array integrity
    countries = protests["countries"]
    assert isinstance(countries, list)
    assert len(countries) == 33
    valid_levels = {"severe", "large", "active"}
    valid_evidence = {"verified", "single", "unverified"}
    for c in countries:
        assert {"name_zh", "region", "level", "evidence"}.issubset(c.keys())
        assert c["level"] in valid_levels
        assert c["evidence"] in valid_evidence

    # Strictly no "60+" decorative claim anywhere in protests_snapshot.json
    assert "60+" not in raw_text


def test_dashboard_protests_panel_rendering_and_counts_match(tmp_path):
    """Verify v0.7.0 protest panel rendering in dashboard.html:
    - Positioned after Regional Crisis Pressures card and before Data Quality card
    - Top country count dynamically matches len(countries)
    - Evidence breakdown counts dynamically match countries array without hardcoded percentages
    - Themes rendered qualitatively without percentages
    - protests_snapshot.json copied to output directory
    """
    out_html = tmp_path / "dashboard.html"
    out_json = tmp_path / "dashboard_data.json"

    data = build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        output_json_path=out_json,
        ui_step=5,
    )
    content = out_html.read_text(encoding="utf-8")

    # 1. Copied protests_snapshot.json to staging/output dir
    copied_protests = tmp_path / "protests_snapshot.json"
    assert copied_protests.exists()
    protests = json.loads(copied_protests.read_text(encoding="utf-8"))
    expected_country_cnt = len(protests["countries"])

    # 2. Section title, subtitle, cutoff badge, and top 3 metrics
    assert "全球抗議活動監測" in content
    assert "生活成本・青年就業・房屋・教育・問責" in content
    assert "數據截點：2026-10-23 · 人工整理快照（非即時數據）" in content
    assert "1,072" in content
    assert "歐洲・美洲・非洲" in content

    # 3. Countries count in top KPI matches len(countries) dynamically
    m_cnt = re.search(
        r'id="protests-country-count"\s+data-count="(\d+)"[^>]*>(\d+)<',
        content,
    )
    assert m_cnt is not None, "protests-country-count element not found"
    assert int(m_cnt.group(1)) == expected_country_cnt
    assert int(m_cnt.group(2)) == expected_country_cnt

    # 4. Evidence counts match countries array dynamically
    expected_ver = sum(1 for c in protests["countries"] if c["evidence"] == "verified")
    expected_sin = sum(1 for c in protests["countries"] if c["evidence"] == "single")
    expected_unv = sum(1 for c in protests["countries"] if c["evidence"] == "unverified")
    assert f'<strong id="protests-ev-verified-cnt">{expected_ver}</strong>' in content
    assert f'<strong id="protests-ev-single-cnt">{expected_sin}</strong>' in content
    assert f'<strong id="protests-ev-unverified-cnt">{expected_unv}</strong>' in content

    # 5. Themes section has no percentages
    themes_block_match = re.search(
        r'id="protests-themes-list">(.*?)</div>\s*<div',
        content,
        re.DOTALL,
    )
    assert themes_block_match is not None
    assert "%" not in themes_block_match.group(1)

    # 6. Section position: after Regional Pressure Cards and before Data Quality Card
    idx_regional = content.index("全球關鍵地緣戰區壓力卡列")
    idx_protests = content.index("全球抗議活動監測")
    idx_quality = content.index("數據品質與審計新鮮度")
    assert idx_regional < idx_protests < idx_quality


def test_dashboard_protests_panel_graceful_hide_when_snapshot_missing(tmp_path):
    """Verify that when protests_snapshot.json is missing, build_dashboard succeeds and hides the panel gracefully."""
    out_html = tmp_path / "dashboard_no_protests.html"
    out_json = tmp_path / "dashboard_no_protests.json"
    missing_path = tmp_path / "does_not_exist_protests.json"

    data = build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        output_json_path=out_json,
        protests_path=missing_path,
        ui_step=5,
    )
    assert out_html.exists()
    assert data["protests"] is None

    content = out_html.read_text(encoding="utf-8")
    assert 'id="protests-monitor-section"' in content
    assert 'data-protests-status="missing"' in content
    assert 'style="display:none;margin-top:24px;"' in content
    assert "全球抗議活動監測" not in content


def test_protests_snapshot_four_countries_updated_values_and_notes():
    """Verify the four updated countries (DE, AT, IE, CH) have correct level, evidence, and note fields."""
    protests_file = Path("data/protests_snapshot.json")
    protests = json.loads(protests_file.read_text(encoding="utf-8"))
    countries = {c["name_zh"]: c for c in protests["countries"]}

    # Germany: level large, evidence verified, with note
    de = countries["德國"]
    assert de["level"] == "large"
    assert de["evidence"] == "verified"
    assert "note" in de
    assert "柏林學校封鎖" in de["note"]
    assert "9/25" in de["note"]
    assert "10/31" in de["note"]
    assert "DW" in de["note"] or "Anadolu" in de["note"]

    # Austria: level large, evidence verified, with note
    at = countries["奧地利"]
    assert at["level"] == "large"
    assert at["evidence"] == "verified"
    assert "note" in at
    assert "10/22" in at["note"]
    assert "維也納" in at["note"]
    assert "ÖH" in at["note"]
    assert "ORF" in at["note"]

    # Ireland: level large, evidence verified, with note
    ie = countries["愛爾蘭"]
    assert ie["level"] == "large"
    assert ie["evidence"] == "verified"
    assert "note" in ie
    assert "都柏林" in ie["note"]
    assert "學費" in ie["note"]
    assert "RTE" in ie["note"]

    # Switzerland: level active (unchanged), evidence verified, with note
    ch = countries["瑞士"]
    assert ch["level"] == "active"
    assert ch["evidence"] == "verified"
    assert "note" in ch
    assert "洛桑" in ch["note"]
    assert "11/20" in ch["note"]
    assert "NZZ" in ch["note"] or "20min" in ch["note"] or "Le Temps" in ch["note"]


def test_protests_snapshot_aggregate_statistics():
    """Verify aggregate statistics after updates: 33 countries, evidence 22/11/0, level 3/14/16."""
    protests_file = Path("data/protests_snapshot.json")
    protests = json.loads(protests_file.read_text(encoding="utf-8"))
    countries = protests["countries"]

    assert len(countries) == 33

    verified = sum(1 for c in countries if c["evidence"] == "verified")
    single = sum(1 for c in countries if c["evidence"] == "single")
    unverified = sum(1 for c in countries if c["evidence"] == "unverified")
    assert verified == 22
    assert single == 11
    assert unverified == 0

    severe = sum(1 for c in countries if c["level"] == "severe")
    large = sum(1 for c in countries if c["level"] == "large")
    active = sum(1 for c in countries if c["level"] == "active")
    assert severe == 3
    assert large == 14
    assert active == 16


def test_generate_dashboard_data_initial_trend_points_matches_worker_api():
    """Verify initial_trend_points matches Worker API daily trend definition:
    - Group by UTC date, take last snapshot per day
    - 10-21 → composite 83.07 (last snapshot 13:44:41Z, pulse 0.0) — HISTORICAL, FIXED
    - 10-22 → composite 87.0 (last snapshot 23:26:36Z, pulse +3.5) — HISTORICAL, FIXED
    - 10-23 → rule-based from current pulse_latest.json (last snapshot of today)
    - Each point's date equals its computed_at UTC date
    - No duplicate dates
    """
    import json
    from pathlib import Path

    model = WW3RiskModel()
    data = generate_dashboard_data(scenario_path="scenarios/baseline_2026.json", model=model)

    points = data["initial_trend_points"]
    assert len(points) == 3

    # Check each point's date matches computed_at UTC date
    for pt in points:
        computed_at = pt["computed_at"]
        expected_date = computed_at[:10]  # YYYY-MM-DD
        assert pt["date"] == expected_date, f"date {pt['date']} != computed_at date {expected_date}"

    # No duplicate dates
    dates = [pt["date"] for pt in points]
    assert len(dates) == len(set(dates)), "Duplicate dates in initial_trend_points"

    # Load current pulse data to compute expected values for today (2026-10-23)
    pulse_file = Path("data/pulse_latest.json")
    with open(pulse_file, "r", encoding="utf-8") as f:
        pulse_data = json.load(f)
    current_pulse_adj = round(float(pulse_data.get("pulse_adjustment", 0.0)), 2)
    current_structural = round(data["main_result"]["global_risk_index"], 2)
    current_composite = round(max(0.0, min(100.0, current_structural + current_pulse_adj)), 2)
    current_computed_at = pulse_data.get("computed_at", "2026-10-23T00:00:00Z")
    current_stage = data["main_result"]["stage"]["number"]

    # Verify historical fixed points (10-21, 10-22) — these days are complete, values won't change
    pt_21 = next(p for p in points if p["date"] == "2026-10-21")
    pt_22 = next(p for p in points if p["date"] == "2026-10-22")
    pt_23 = next(p for p in points if p["date"] == "2026-10-23")

    assert pt_21["composite_index"] == 83.07
    assert pt_21["structural_index"] == 83.07
    assert pt_21["pulse_adjustment"] == 0.0
    assert pt_21["computed_at"] == "2026-10-21T13:44:41Z"

    assert pt_22["composite_index"] == 87.0
    assert pt_22["structural_index"] == 83.5
    assert pt_22["pulse_adjustment"] == 3.5
    assert pt_22["computed_at"] == "2026-10-22T23:26:36Z"

    # Verify today's point (10-23) using rule-based expectations from current pulse data
    assert pt_23["date"] == "2026-10-23"
    assert pt_23["computed_at"] == current_computed_at
    assert pt_23["structural_index"] == current_structural
    assert pt_23["pulse_adjustment"] == current_pulse_adj
    assert pt_23["composite_index"] == current_composite
    assert pt_23["stage"] == current_stage


def test_render_trend_svg_dynamic_y_axis_and_value_labels():
    """Verify render_trend_svg produces dynamic Y-axis, value labels, and handles monthly single point."""
    # Daily mode with 3 points
    daily_points = [
        {"date": "2026-10-21", "computed_at": "2026-10-21T13:44:41Z", "composite_index": 83.07, "structural_index": 83.07, "pulse_adjustment": 0.0, "stage": 3},
        {"date": "2026-10-22", "computed_at": "2026-10-22T23:26:36Z", "composite_index": 87.0, "structural_index": 83.5, "pulse_adjustment": 3.5, "stage": 3},
        {"date": "2026-10-23", "computed_at": "2026-10-23T08:26:31Z", "composite_index": 87.1, "structural_index": 83.5, "pulse_adjustment": 3.6, "stage": 3},
    ]
    svg = render_trend_svg(daily_points, granularity="daily")
    # Dynamic Y-axis note
    assert "Y 軸按數據範圍動態縮放（非 0–100）" in svg
    # Value labels on composite points (1 decimal)
    assert "83.1" in svg or "83.0" in svg  # 83.07 rounded to 1 decimal
    assert "87.0" in svg
    assert "87.1" in svg
    # X-axis labels for all points (≤7)
    assert "2026-10-21" in svg
    assert "2026-10-22" in svg
    assert "2026-10-23" in svg
    # Both composite and structural lines
    assert "f59e0b" in svg  # composite color
    assert "rgba(255,255,255,0.4)" in svg  # structural color

    # Monthly mode with single point
    monthly_single = [{"month": "2026-10", "composite_index": 85.5, "structural_index": 83.5, "n_days": 3}]
    svg_monthly = render_trend_svg(monthly_single, granularity="monthly")
    # Single point: dot + value + hint, no line
    assert "資料累積中" in svg_monthly
    assert "85.5" in svg_monthly
    # No polyline for single point
    assert "polyline" not in svg_monthly or "points=" not in svg_monthly










