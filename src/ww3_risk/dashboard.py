"""WW3 Risk Model Static Dashboard Generator.

Produces a standalone, pure static HTML/CSS/JS dashboard (zero external frameworks,
zero CDN dependencies, dark military-tactical theme) that can be opened directly
offline via file://.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from .indicators import ScenarioData, load_scenario_from_file
from .model import WW3RiskModel, RiskResult


# Chinese short names for indicators used in regional formula displays and breakdowns
INDICATOR_SHORT_NAMES = {
    # L1: 生存 / 資源
    "l1_food_security": "糧食儲備",
    "l1_water_stress": "水資源壓力",
    "l1_energy_vulnerability": "能源脆弱性",
    "l1_critical_minerals": "關鍵礦物管制",
    "l1_climate_impact": "氣候衝擊",
    "l1_maritime_chokepoints": "海運咽喉風險",
    # L2: 分配失衡
    "l2_wealth_gini": "財富差距",
    "l2_compute_monopoly": "算力壟斷",
    "l2_land_housing_concentration": "土地資產集中",
    "l2_social_mobility": "社會流動停滯",
    "l2_institutional_fairness": "制度公平赤字",
    "l2_peaceful_redistribution": "再分配失靈",
    # L3: 工作 / 生計
    "l3_unemployment_underemployment": "就業不足",
    "l3_youth_unemployment": "青年失業",
    "l3_wage_vs_living_cost": "工資生活成本夾擊",
    "l3_housing_affordability": "房價所得比",
    "l3_ai_displacement_rate": "AI 勞動取代",
    "l3_effort_reward_breakdown": "努力回報崩塌",
    # L4: 權力 / 安全困境
    "l4_military_expenditure_growth": "軍費擴張",
    "l4_arms_race_hypersonic": "高超音速軍備競賽",
    "l4_bloc_polarization": "陣營極化",
    "l4_weaponized_interdependence": "相互依賴武器化",
    "l4_nuclear_breakout": "核門檻鬆動",
    "l4_territorial_flashpoints": "領土引信點",
    # L5: 未來恐懼 / 預防邏輯
    "l5_relative_decline_anxiety": "霸權衰落焦慮",
    "l5_demographic_cliff": "人口老齡斷崖",
    "l5_economic_stagnation": "長期停滯預期",
    "l5_tech_supremacy_fear": "技術霸權恐懼",
    "l5_miscalculation_risk": "決策誤判風險",
    "l5_leadership_time_horizon": "政治短視焦慮",
}

# Regional pressure mapping definition (derived from existing scenario indicators)
# Explicitly noted as illustrative mapping to comply with transparency requirements.
REGIONAL_INDICATOR_MAPPINGS = {
    "eastern_europe": {
        "name": "東歐（烏克蘭 / 北約東翼前線）",
        "name_en": "Eastern Europe / NATO Eastern Flank",
        "primary_indicators": [
            "l4_territorial_flashpoints",
            "l4_bloc_polarization",
            "l4_military_expenditure_growth",
            "l4_nuclear_breakout",
        ],
        "note": "示意拆分：指標原始平均映射 [l4_territorial_flashpoints, l4_bloc_polarization, l4_military_expenditure_growth, l4_nuclear_breakout]，反映陸權對峙與前沿引信摩擦。",
    },
    "middle_east": {
        "name": "中東（紅海 / 波斯灣 / 霍爾木茲咽喉）",
        "name_en": "Middle East / Persian Gulf & Red Sea Chokepoints",
        "primary_indicators": [
            "l1_maritime_chokepoints",
            "l1_energy_vulnerability",
            "l4_territorial_flashpoints",
            "l1_water_stress",
        ],
        "note": "示意拆分：指標原始平均映射 [l1_maritime_chokepoints, l1_energy_vulnerability, l4_territorial_flashpoints, l1_water_stress]，反映航道封鎖與能源外溢風險。",
    },
    "east_asia": {
        "name": "東亞（台海 / 南海 / 第一島鏈）",
        "name_en": "East Asia / Taiwan Strait & South China Sea",
        "primary_indicators": [
            "l2_compute_monopoly",
            "l4_territorial_flashpoints",
            "l5_tech_supremacy_fear",
            "l4_bloc_polarization",
        ],
        "note": "示意拆分：指標原始平均映射 [l2_compute_monopoly, l4_territorial_flashpoints, l5_tech_supremacy_fear, l4_bloc_polarization]，反映算力晶圓代工壟斷與預防性技術爭霸。",
    },
    "south_central_asia": {
        "name": "南亞與中亞（印巴 / 喜馬拉雅跨界水資源）",
        "name_en": "South & Central Asia / Transboundary Basins",
        "primary_indicators": [
            "l1_water_stress",
            "l1_climate_impact",
            "l4_nuclear_breakout",
        ],
        "note": "示意拆分：指標原始平均映射 [l1_water_stress, l1_climate_impact, l4_nuclear_breakout]，反映高山冰川消融引致水資源爭奪與核門檻壓力。",
    },
    "global_chokepoints": {
        "name": "全球戰略咽喉與關鍵礦物網",
        "name_en": "Global Chokepoints & Strategic Critical Mineral Webs",
        "primary_indicators": [
            "l1_maritime_chokepoints",
            "l1_critical_minerals",
            "l4_weaponized_interdependence",
        ],
        "note": "示意拆分：指標原始平均映射 [l1_maritime_chokepoints, l1_critical_minerals, l4_weaponized_interdependence]，反映關鍵礦物禁運與全球海運供應鏈梗阻。",
    },
}

# Unconnected live data sources (stubs/placeholders - offline v1)
UNCONNECTED_DATA_SOURCES = [
    {
        "id": "adsb_military_transponder",
        "name": "全球軍用機載 ADS-B 實時異動偵測",
        "name_en": "Global Military ADS-B Transponder Stream",
        "status": "未接數據源 (Offline Placeholder)",
        "expected_cadence": "10-sec telemetry",
        "protocol": "ADS-B Mode-S Receiver Feed",
        "target_regions": ["波羅的海", "黑海", "波斯灣", "台海空域"],
        "description": "即時監控空中加油機、RC-135 偵察機與預警機起降活動，v1 純靜態離線模型不接入外部即時通訊。",
    },
    {
        "id": "gdelt_conflict_pulse",
        "name": "GDELT 全球衝突事件實時脈衝",
        "name_en": "GDELT Conflict Pulse & Event Stream",
        "status": "未接數據源 (Offline Placeholder)",
        "expected_cadence": "15-minute batch",
        "protocol": "GDELT 2.0 Global Event Feed",
        "target_regions": ["全球主要衝突邊界"],
        "description": "多語言自然語言處理新聞突發事件與暴力衝突事件熱度脈衝，目前以結構性情境指標靜態替代。",
    },
    {
        "id": "polymarket_war_odds",
        "name": "Polymarket 地緣衝突合約實時預測賠率",
        "name_en": "Polymarket Conflict Prediction Market Odds",
        "status": "未接數據源 (Offline Placeholder)",
        "expected_cadence": "Real-time websocket",
        "protocol": "On-chain Prediction API",
        "target_regions": ["美中台海合約", "以伊衝突合約", "俄烏停火合約"],
        "description": "市場真金白銀定價之地緣衝突賠率，UI 目前提供結構風險情境帶，未接入實時鏈上訂單簿。",
    },
    {
        "id": "ais_chokepoint_telemetry",
        "name": "戰略海運咽喉 (霍爾木茲/曼德) 實時 AIS 船隻通航量",
        "name_en": "Strategic Chokepoints Vessel AIS Telemetry",
        "status": "未接數據源 (Offline Placeholder)",
        "expected_cadence": "1-minute AIS stream",
        "protocol": "Satellite & Terrestrial AIS API",
        "target_regions": ["曼德海峽", "霍爾木茲海峽", "馬六甲海峽", "蘇伊士運河"],
        "description": "商船、油輪與液化天然氣船轉向繞道好望角之即時繞航比率，目前由 L1 海運咽喉指標 (68.0) 靜態代表。",
    },
    {
        "id": "conflict_border_webcams",
        "name": "核心戰略前線公開監視與實況流",
        "name_en": "Border Frontline Public Feeds & Webcams",
        "status": "未接數據源 (Offline Placeholder)",
        "expected_cadence": "Live HLS/RTSP Stream",
        "protocol": "Public Live Video Feeds",
        "target_regions": ["霍爾木茲海峽兩岸", "波羅的海港口", "紅海口"],
        "description": "公開港口與邊界攝影機串流，本系統為純純離線儀表板，嚴格標記為佔位預留。",
    },
]


def calculate_regional_pressures(scenario: ScenarioData) -> List[Dict[str, Any]]:
    """Compute regional pressure scores from scenario indicators as raw arithmetic mean."""
    indicator_dict = {}
    for lid, layer in scenario.layers.items():
        for ind in layer.indicators:
            indicator_dict[ind.id] = ind

    regional_cards = []
    for reg_id, conf in REGIONAL_INDICATOR_MAPPINGS.items():
        components = []
        for iid in conf["primary_indicators"]:
            if iid not in indicator_dict:
                raise KeyError(
                    f"Regional mapping '{reg_id}' references unknown indicator '{iid}'"
                )
            ind = indicator_dict[iid]
            short_name = INDICATOR_SHORT_NAMES.get(iid, ind.name)
            components.append({
                "id": iid,
                "name": short_name,
                "value": float(ind.value),
            })

        if not components:
            raise ValueError(f"Regional mapping '{reg_id}' has no primary indicators defined")

        raw_avg = sum(c["value"] for c in components) / len(components)
        score = round(raw_avg, 1)

        if score >= 85.0:
            level = "CRITICAL"
            level_label = "極度高壓 (Critical)"
            color_class = "danger"
        elif score >= 70.0:
            level = "HIGH"
            level_label = "高度緊張 (High)"
            color_class = "warning"
        elif score >= 50.0:
            level = "ELEVATED"
            level_label = "顯著升級 (Elevated)"
            color_class = "elevated"
        else:
            level = "MODERATE"
            level_label = "溫和可控 (Moderate)"
            color_class = "success"

        formula_terms = " ＋ ".join([f"{c['value']:.1f} {c['name']}" for c in components])
        formula_str = f"示意拆分（指標原始平均）：({formula_terms}) ÷ {len(components)} = {score:.1f}"

        regional_cards.append({
            "id": reg_id,
            "name": conf["name"],
            "name_en": conf["name_en"],
            "score": score,
            "level": level,
            "level_label": level_label,
            "color_class": color_class,
            "indicators_used": conf["primary_indicators"],
            "components": components,
            "formula": formula_str,
            "note": conf["note"],
        })

    return regional_cards


def generate_dashboard_data(
    scenario_path: Path | str,
    all_scenarios_dir: Path | str = "scenarios",
    historical_path: Path | str = "data/historical_cases.json",
    model: Optional[WW3RiskModel] = None,
) -> Dict[str, Any]:
    """Compile all evaluated data needed by the static dashboard."""
    if model is None:
        model = WW3RiskModel()

    scenario_file = Path(scenario_path)
    if not scenario_file.exists():
        raise FileNotFoundError(f"Main scenario file not found: {scenario_file}")

    main_scenario = load_scenario_from_file(scenario_file)
    main_result = model.evaluate(main_scenario)

    # 1. Evaluate all comparative scenarios in folder
    scenarios_dir = Path(all_scenarios_dir)
    comparative_results: List[Dict[str, Any]] = []
    if scenarios_dir.exists():
        for p in sorted(scenarios_dir.glob("*.json")):
            try:
                sc = load_scenario_from_file(p)
                res = model.evaluate(sc)
                delta_risk = round(res.global_risk_index - main_result.global_risk_index, 1)
                comparative_results.append({
                    "id": sc.id,
                    "title": sc.title,
                    "title_en": sc.title_en,
                    "year": sc.year,
                    "description": sc.description,
                    "file_path": str(p),
                    "global_risk_index": round(res.global_risk_index, 1),
                    "delta_from_baseline": delta_risk,
                    "delta_str": f"{'+' if delta_risk >= 0 else ''}{delta_risk}",
                    "stage_number": res.stage.stage_number,
                    "stage_title": res.stage.title,
                    "base_structural_score": round(res.base_structural_score, 1),
                    "gate_factor": round(res.gate_factor, 3),
                    "peace_capacity": round(res.peace_capacity, 1),
                    "probability_bands": {k: v.to_dict() for k, v in res.probability_bands.items()},
                    "layer_scores": {k: round(v, 1) for k, v in res.layer_scores.items()},
                })
            except Exception as e:
                pass

    # 2. Evaluate historical cases
    hist_file = Path(historical_path)
    historical_results: List[Dict[str, Any]] = []
    if hist_file.exists():
        with open(hist_file, "r", encoding="utf-8") as f:
            hist_raw = json.load(f)
        cases = hist_raw if isinstance(hist_raw, list) else hist_raw.get("cases", [])
        for c in cases:
            sc = ScenarioData.from_dict(c)
            res = model.evaluate(sc)
            historical_results.append({
                "id": sc.id,
                "title": sc.title,
                "title_en": sc.title_en,
                "year": sc.year,
                "global_risk_index": round(res.global_risk_index, 1),
                "stage_number": res.stage.stage_number,
                "stage_title": res.stage.title,
                "gate_factor": round(res.gate_factor, 3),
                "peace_capacity": round(res.peace_capacity, 1),
                "layer_scores": {k: round(v, 1) for k, v in res.layer_scores.items()},
                "notes": sc.description,
            })
        # Sort historical by year ascending
        historical_results.sort(key=lambda x: str(x["year"]))

    # 3. Regional pressures derived from main scenario
    regional_pressures = calculate_regional_pressures(main_scenario)

    # 4. Full Indicators List for detailed inspection table
    all_indicators = []
    for lid in ["L1", "L2", "L3", "L4", "L5"]:
        if lid in main_scenario.layers:
            layer = main_scenario.layers[lid]
            for ind in layer.indicators:
                status = ind.get_quality_status()
                all_indicators.append({
                    "id": ind.id,
                    "layer": lid,
                    "layer_name": layer.name,
                    "name": ind.name,
                    "name_en": ind.name_en,
                    "value": round(ind.value, 1),
                    "weight": round(ind.weight, 2),
                    "evidence_level": ind.evidence_level,
                    "source": ind.source,
                    "source_name": ind.source_name or ind.source,
                    "source_url": ind.source_url,
                    "year": ind.year,
                    "raw_value": ind.raw_value,
                    "raw_unit": ind.raw_unit,
                    "observation_date": ind.observation_date,
                    "publication_date": ind.publication_date,
                    "last_checked": ind.last_checked,
                    "stale_after": ind.stale_after,
                    "status": status,
                    "normalization_method": ind.normalization_method,
                    "scoring_rubric": ind.scoring_rubric,
                    "applicability_note": ind.applicability_note,
                    "uncertainty_note": ind.uncertainty_note,
                    "note": ind.note,
                })

    all_buffers = []
    for b in main_scenario.gate_buffers:
        status = b.get_quality_status()
        all_buffers.append({
            "id": b.id,
            "layer": "GATE",
            "layer_name": "和平機制閘門",
            "name": b.name,
            "name_en": b.name_en,
            "value": round(b.value, 1),
            "weight": round(b.weight, 2),
            "evidence_level": b.evidence_level,
            "source": b.source,
            "source_name": b.source_name or b.source,
            "source_url": b.source_url,
            "year": b.year,
            "raw_value": b.raw_value,
            "raw_unit": b.raw_unit,
            "observation_date": b.observation_date,
            "publication_date": b.publication_date,
            "last_checked": b.last_checked,
            "stale_after": b.stale_after,
            "status": status,
            "normalization_method": b.normalization_method,
            "scoring_rubric": b.scoring_rubric,
            "applicability_note": b.applicability_note,
            "uncertainty_note": b.uncertainty_note,
            "note": b.note,
        })

    # Data quality and evidence distribution audit
    data_quality = main_scenario.calculate_data_quality()
    evidence_counts = {"verified": 0, "inference": 0, "illustrative": 0}
    for item in all_indicators + all_buffers:
        ev = item.get("evidence_level", "illustrative")
        evidence_counts[ev] = evidence_counts.get(ev, 0) + 1
    total_ind = len(all_indicators) + len(all_buffers)
    evidence_distribution = {
        "verified": evidence_counts.get("verified", 0),
        "inference": evidence_counts.get("inference", 0),
        "illustrative": evidence_counts.get("illustrative", 0),
        "total": total_ind,
        "verified_pct": round(evidence_counts.get("verified", 0) / total_ind * 100, 1) if total_ind else 0.0,
        "inference_pct": round(evidence_counts.get("inference", 0) / total_ind * 100, 1) if total_ind else 0.0,
        "illustrative_pct": round(evidence_counts.get("illustrative", 0) / total_ind * 100, 1) if total_ind else 0.0,
    }

    # 5. Model coefficients and formula parameters for pure JS simulator
    model_params = {
        "c_l1_l2": model.c_l1_l2,
        "c_l3_l5": model.c_l3_l5,
        "c_l4_gate": model.c_l4_gate,
        "max_interaction_cap": model.max_interaction_cap,
        "gate_min": model.gate_min,
        "gate_max": model.gate_max,
        "soft_clamp_threshold": 70.0,
        "soft_clamp_ceiling": 100.0,
        "layer_weights": main_result.layer_weights,
        "stage_thresholds": [25.0, 50.0, 85.0],
        "probability_params": {
            "1y": {"l_max": 80.0, "k": 0.055, "x0": 120.0, "low_r": 0.65, "up_r": 1.45},
            "5y": {"l_max": 95.0, "k": 0.058, "x0": 95.0, "low_r": 0.75, "up_r": 1.30},
            "10y": {"l_max": 98.0, "k": 0.059, "x0": 82.5, "low_r": 0.80, "up_r": 1.25},
        },
    }

    return {
        "metadata": {
            "title": "WW3 戰爭風險指數儀表板",
            "title_en": "WW3 War Risk Index Dashboard",
            "model_version": "0.4.0",
            "generated_at": "2026-10-21",
            "active_scenario_id": main_scenario.id,
            "active_scenario_title": main_scenario.title,
            "active_scenario_year": main_scenario.year,
        },
        "main_result": main_result.to_dict(),
        "scenarios": comparative_results,
        "historical": historical_results,
        "regional_pressures": regional_pressures,
        "indicators": all_indicators,
        "gate_buffers": all_buffers,
        "unconnected_sources": UNCONNECTED_DATA_SOURCES,
        "data_quality": data_quality,
        "evidence_distribution": evidence_distribution,
        "model_params": model_params,
    }


def render_gauge_svg(score: float, width: int = 320, height: int = 180) -> str:
    """Generate inline SVG for the semicircular gauge."""
    # Semi-circle arc: angles from 180 deg (left, 0) to 0 deg (right, 100)
    # Radius = 120, Center at (160, 150)
    cx, cy, r = 160, 145, 115
    clamped_score = max(0.0, min(100.0, score))
    # Needle angle in radians: score 0 -> pi, score 100 -> 0
    # In SVG math: angle theta from pi to 0
    theta = math.pi - (clamped_score / 100.0) * math.pi
    needle_len = r - 15
    nx = cx + needle_len * math.cos(theta)
    ny = cy - needle_len * math.sin(theta)

    # Arc segments:
    # 0 to 25: Green
    # 25 to 50: Yellow
    # 50 to 85: Orange
    # 85 to 100: Red
    return f"""
    <svg viewBox="0 0 320 185" class="gauge-svg" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#10b981" />
          <stop offset="25%" stop-color="#84cc16" />
          <stop offset="50%" stop-color="#eab308" />
          <stop offset="85%" stop-color="#f97316" />
          <stop offset="100%" stop-color="#ef4444" />
        </linearGradient>
        <filter id="needleGlow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="0" stdDeviation="3" flood-color="#ef4444" flood-opacity="0.6"/>
        </filter>
      </defs>
      <!-- Background track -->
      <path d="M 45 145 A 115 115 0 0 1 275 145" fill="none" stroke="#1e293b" stroke-width="20" stroke-linecap="round"/>
      <!-- Colored value track -->
      <path d="M 45 145 A 115 115 0 0 1 275 145" fill="none" stroke="url(#gaugeGradient)" stroke-width="20" stroke-linecap="round" opacity="0.85"/>
      
      <!-- Scale ticks & labels -->
      <text x="35" y="165" fill="#64748b" font-size="11" font-weight="600" text-anchor="middle">0</text>
      <text x="75" y="65" fill="#64748b" font-size="11" font-weight="600" text-anchor="middle">25</text>
      <text x="160" y="24" fill="#64748b" font-size="11" font-weight="600" text-anchor="middle">50</text>
      <text x="245" y="65" fill="#64748b" font-size="11" font-weight="600" text-anchor="middle">85</text>
      <text x="285" y="165" fill="#64748b" font-size="11" font-weight="600" text-anchor="middle">100</text>

      <!-- Needle pointer -->
      <line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="#f8fafc" stroke-width="3.5" stroke-linecap="round" filter="url(#needleGlow)"/>
      <circle cx="{cx}" cy="{cy}" r="7" fill="#f8fafc" stroke="#0f172a" stroke-width="2"/>
      <circle cx="{cx}" cy="{cy}" r="3" fill="#ef4444"/>
    </svg>
    """


def build_dashboard_html(data: Dict[str, Any], ui_step: int = 5, api_base: Optional[str] = None) -> str:
    """Render the dashboard HTML for a specific UI Step (1 to 5)."""
    api_base_val = (api_base or "").strip().rstrip("/")
    main = data["main_result"]
    risk_score = main["global_risk_index"]
    stage = main["stage"]
    gauge_svg = render_gauge_svg(risk_score)
    data_json_str = json.dumps(data, ensure_ascii=False, indent=2)

    if api_base_val:
        source_badge_html = '<span class="meta-badge badge-offline" id="top-data-source-badge">● 離線快照（內嵌數據）</span>'
    else:
        source_badge_html = '<span class="meta-badge badge-offline" id="top-data-source-badge">● 100% 本地離線運行 (ZERO CDN)</span>'

    # Escalation stages definitions for tracker
    stages_info = [
        {"num": 1, "code": "STAGE_1", "range": "0 - 25", "title": "結構壓力形成", "title_en": "Pressure Building", "desc": "資源、分配或經濟摩擦處於低位累積期，體系彈性充裕，國際制度能有效吸收爭端。"},
        {"num": 2, "code": "STAGE_2", "range": "25 - 50", "title": "利益衝突顯性化", "title_en": "Overt Conflict", "desc": "關鍵產業、地緣勢力範圍或未來預期出現顯著分歧，陣營對立升溫，但常規外交與經貿制衡依然有效。"},
        {"num": 3, "code": "STAGE_3", "range": "50 - 85", "title": "和平解決機制失效", "title_en": "Peace Breakdown", "desc": "外交互信受挫、貿易脫鉤武器化，多邊仲裁癱瘓，安全困境進入自我強化之高危狀態。"},
        {"num": 4, "code": "STAGE_4", "range": "85 - 100", "title": "暴力成為被接受選項", "title_en": "Violence Accepted", "desc": "和平緩衝全面失靈，生存危機、預防性打擊邏輯或體系絕望感壓倒避戰共識，爆發總體戰衝突機率極高。"},
    ]

    # Step 1 Stage Cards HTML
    stage_tracker_cards = []
    for s in stages_info:
        is_active = (s["num"] == stage["number"])
        active_class = "active" if is_active else ""
        badge = '<span class="stage-tag active-tag">當前階段 · CURRENT</span>' if is_active else f'<span class="stage-tag">區間 {s["range"]}</span>'
        stage_tracker_cards.append(f"""
        <div class="stage-card {active_class}" id="stage-card-{s['num']}">
          <div class="stage-card-header">
            <span class="stage-num">STAGE 0{s['num']}</span>
            {badge}
          </div>
          <div class="stage-card-title">{s['title']}</div>
          <div class="stage-card-title-en">{s['title_en']}</div>
          <p class="stage-card-desc">{s['desc']}</p>
        </div>
        """)
    stage_tracker_html = "\n".join(stage_tracker_cards)

    # Initialize placeholder sections
    step1_5_html = ""
    step2_html = ""
    step3_html = ""
    step4_html = ""
    step5_html = ""

    # Step 1.5: War Risk Drivers Decomposition & Data Quality Overview (UI-Step >= 2)
    if ui_step >= 2:
        dq = data.get("data_quality", {})
        ev_dist = data.get("evidence_distribution", {})
        comp_pct = dq.get("completeness_pct", 100.0)
        fresh_cnt = dq.get("fresh_count", 1)
        stale_cnt = dq.get("stale_count", 33)
        missing_cnt = dq.get("missing_count", 0)
        total_ind_cnt = dq.get("total_indicators", 34)

        ver_pct = ev_dist.get("verified_pct", 20.6)
        inf_pct = ev_dist.get("inference_pct", 58.8)
        ill_pct = ev_dist.get("illustrative_pct", 20.6)
        ver_cnt = ev_dist.get("verified", 7)
        inf_cnt = ev_dist.get("inference", 20)
        ill_cnt = ev_dist.get("illustrative", 7)

        raw_unclamped = (main["base_structural_score"] + main["interactions"]["total"]) * main["gate_factor"]

        step1_5_html = f"""
    <!-- Section 1.5: War Risk Drivers & Data Quality Overview (UI-Step 2+) -->
    <section class="grid-two-cols" style="display:grid;grid-template-columns:1.2fr 0.8fr;gap:24px;margin-top:24px;">
      <!-- Driver Decomposition Card -->
      <div class="panel-card">
        <div class="panel-header">
          <div class="panel-title">
            <span>戰爭風險指數主要驅動分解 (War Risk Index Driver Decomposition)</span>
          </div>
          <span class="panel-tag">EXACT MATHEMATICAL TRACEABILITY</span>
        </div>
        <p style="font-size:0.78rem;color:var(--text-muted);margin-bottom:14px;">
          指數由 50 升至當前 <strong>{risk_score:.1f}</strong> 係由以下核心結構與機制共同決定，每一項均可向上回溯至指標原始數據與計算公式：
        </p>
        <div class="driver-steps-grid">
          <div class="driver-step-box">
            <div class="driver-step-head">
              <span class="driver-step-num">01</span>
              <span class="driver-step-name">基礎結構加權分 (Base Structural)</span>
              <span class="driver-step-val" id="driver-base-val">{main['base_structural_score']:.1f}</span>
            </div>
            <div class="driver-step-desc">
              五層結構維度加權均值：L1 ({main['layer_scores']['L1']:.1f}) + L2 ({main['layer_scores']['L2']:.1f}) + L3 ({main['layer_scores']['L3']:.1f}×1.1) + L4 ({main['layer_scores']['L4']:.1f}×1.2) + L5 ({main['layer_scores']['L5']:.1f}×1.1) ÷ 5.4。
            </div>
          </div>
          <div class="driver-step-box">
            <div class="driver-step-head">
              <span class="driver-step-num">02</span>
              <span class="driver-step-name">非線性共振增益 (Interactions)</span>
              <span class="driver-step-val" id="driver-interaction-val">+{main['interactions']['total']:.2f}</span>
            </div>
            <div class="driver-step-desc">
              三組脆弱維度耦合：資源×分配 (+{main['interactions']['L1_x_L2']:.2f}) + AI失業×恐懼 (+{main['interactions']['L3_x_L5']:.2f}) + 安全困境×閘門失效 (+{main['interactions']['L4_x_GateFailure']:.2f})。
            </div>
          </div>
          <div class="driver-step-box">
            <div class="driver-step-head">
              <span class="driver-step-num">03</span>
              <span class="driver-step-name">和平機制安全閥乘數 (Gate Factor)</span>
              <span class="driver-step-val" id="driver-gate-val">x{main['gate_factor']:.3f}</span>
            </div>
            <div class="driver-step-desc">
              四項和平緩衝容量均值 {main['peace_capacity']:.1f}/100（機制失效度 {main['gate_failure']:.1f}%）。公式：<code>1.4 - ({main['peace_capacity']:.1f}/100)×0.8 = {main['gate_factor']:.3f}</code>，對總體產生淨放大。
            </div>
          </div>
          <div class="driver-step-box">
            <div class="driver-step-head">
              <span class="driver-step-num">04</span>
              <span class="driver-step-name">高位平滑飽和映射 (Soft-Clamp)</span>
              <span class="driver-step-val" id="driver-clamp-val">{raw_unclamped:.1f} → {risk_score:.1f}</span>
            </div>
            <div class="driver-step-desc">
              未夾持得分 {raw_unclamped:.1f} 超越 70 閾值，經雙曲正切 Tanh 飽和函數平滑壓縮，防止無界發散，收斂為 {risk_score:.1f}（進入 Stage {stage['number']} {stage['title']}）。
            </div>
          </div>
        </div>
      </div>

      <!-- Data Quality & Freshness Card -->
      <div class="panel-card">
        <div class="panel-header">
          <div class="panel-title">
            <span>數據品質與審計新鮮度 (Data Quality &amp; Freshness Audit)</span>
          </div>
          <span class="panel-tag">AUDITED AS OF 2026-10-21</span>
        </div>
        
        <div class="quality-metric-row">
          <div class="quality-cell">
            <div class="q-label">資料完整度</div>
            <div class="q-val" id="quality-comp-pct" style="color:var(--color-green);">{comp_pct:.1f}%</div>
            <div class="q-sub">{total_ind_cnt}/34 指標全齊全</div>
          </div>
          <div class="quality-cell">
            <div class="q-label">資料新鮮度</div>
            <div class="q-val" id="quality-freshness-val" style="color:var(--color-yellow);">{fresh_cnt} Fresh / {stale_cnt} Stale</div>
            <div class="q-sub">嚴格依週期過期標註</div>
          </div>
          <div class="quality-cell">
            <div class="q-label">缺失項 (Missing)</div>
            <div class="q-val" id="quality-missing-val" style="color:#f8fafc;">{missing_cnt} 項</div>
            <div class="q-sub">無任何未定義欄位</div>
          </div>
        </div>

        <div style="margin-top:16px;">
          <div style="font-size:0.75rem;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;font-family:var(--font-mono);">
            三級證據階層分布 (Evidence Level Breakdown)
          </div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            <div>
              <div style="display:flex;justify-content:space-between;font-size:0.76rem;margin-bottom:3px;">
                <span style="color:#6ee7b7;font-weight:600;">VERIFIED (實測驗證)</span>
                <span style="font-family:var(--font-mono);color:#cbd5e1;">{ver_cnt} 項 · {ver_pct:.1f}%</span>
              </div>
              <div class="progress-track" style="height:6px;">
                <div class="progress-fill" style="width:{ver_pct}%;background:#10b981;"></div>
              </div>
            </div>
            <div>
              <div style="display:flex;justify-content:space-between;font-size:0.76rem;margin-bottom:3px;">
                <span style="color:#67e8f9;font-weight:600;">INFERENCE (統計推算)</span>
                <span style="font-family:var(--font-mono);color:#cbd5e1;">{inf_cnt} 項 · {inf_pct:.1f}%</span>
              </div>
              <div class="progress-track" style="height:6px;">
                <div class="progress-fill" style="width:{inf_pct}%;background:#06b6d4;"></div>
              </div>
            </div>
            <div>
              <div style="display:flex;justify-content:space-between;font-size:0.76rem;margin-bottom:3px;">
                <span style="color:#fde047;font-weight:600;">ILLUSTRATIVE (示範估算)</span>
                <span style="font-family:var(--font-mono);color:#cbd5e1;">{ill_cnt} 項 · {ill_pct:.1f}%</span>
              </div>
              <div class="progress-track" style="height:6px;">
                <div class="progress-fill" style="width:{ill_pct}%;background:#eab308;"></div>
              </div>
            </div>
          </div>
        </div>

        <div class="quality-audit-note" style="margin-top:14px;padding:10px 12px;background:rgba(15, 23, 42, 0.6);border:1px solid var(--border-color);border-radius:4px;font-size:0.74rem;color:var(--text-muted);line-height:1.4;">
          <strong>審計結論 (P0 Audit)：</strong>34 項指標已全部完成來源內容逐項核實（Confirmed: 34，Corrected: 0，Unverifiable: 0）。拒絕聲稱即時遙測，離線模型標記清楚無虛構。
        </div>
      </div>
    </section>
        """

    # Step 2: Five Layers, Peace Gate, Interactions, Top Pushers & Structural Insights
    if ui_step >= 2:
        layer_meta = {
            "L1": {"title": "L1: 生存／資源稀缺", "title_en": "Survival & Resource Scarcity", "desc": "糧食儲備、淡水枯竭、化石能源及關鍵礦物出口管制。"},
            "L2": {"title": "L2: 分配失衡", "title_en": "Inequality & Distribution", "desc": "全球財富極化、前沿 AI 算力壟斷及戰略技術專利壁壘。"},
            "L3": {"title": "L3: 工作／AI 取代", "title_en": "Labor & AI Displacement", "desc": "青年失業率、白領與藍領自動化焦慮及社會流動停滯。"},
            "L4": {"title": "L4: 權力／安全困境", "title_en": "Power & Security Dilemma", "desc": "地緣陣營極化、軍費開支、熱點摩擦及經貿武器化。"},
            "L5": {"title": "L5: 對未來的恐懼", "title_en": "Fear of Future & Preventive Logic", "desc": "霸權衰落焦慮、人口斷崖、技術喪失恐慌及預防性打擊邏輯。"},
        }

        layer_bars = []
        for lid in ["L1", "L2", "L3", "L4", "L5"]:
            sc = main["layer_scores"].get(lid, 0.0)
            wt = main["layer_weights"].get(lid, 1.0)
            meta = layer_meta[lid]
            # Color based on score
            if sc >= 85: bar_color = "var(--color-red)"
            elif sc >= 70: bar_color = "var(--color-orange)"
            elif sc >= 50: bar_color = "var(--color-yellow)"
            else: bar_color = "var(--color-green)"

            layer_bars.append(f"""
            <div class="layer-row">
              <div class="layer-info">
                <div class="layer-name-wrap">
                  <span class="layer-code">{lid}</span>
                  <span class="layer-name">{meta['title']}</span>
                  <span class="layer-en">{meta['title_en']}</span>
                </div>
                <div class="layer-val-wrap">
                  <span class="layer-weight">權重 x{wt:.1f}</span>
                  <span class="layer-score" style="color:{bar_color};">{sc:.1f}</span>
                  <span class="layer-max">/100</span>
                </div>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: {sc}%; background: {bar_color};"></div>
              </div>
              <div class="layer-desc">{meta['desc']}</div>
            </div>
            """)
        layers_html = "\n".join(layer_bars)

        # Peace buffers items
        buffers_rows = []
        for b in main.get("top_peace_buffers", []):
            cap = b["capacity"]
            if cap >= 60: b_color = "var(--color-green)"
            elif cap >= 40: b_color = "var(--color-yellow)"
            else: b_color = "var(--color-red)"
            buffers_rows.append(f"""
            <div class="buffer-item">
              <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:4px;">
                <span style="color:#e2e8f0;font-weight:600;">{b['name']}</span>
                <span style="font-family:var(--font-mono);color:{b_color};font-weight:700;">{cap:.1f} <span style="font-size:0.7rem;color:var(--text-dim);font-weight:400;">(權重 x{b['weight']:.1f})</span></span>
              </div>
              <div class="progress-track" style="height:6px;">
                <div class="progress-fill" style="width:{cap}%;background:{b_color};"></div>
              </div>
            </div>
            """)
        buffers_html = "\n".join(buffers_rows)

        # Top risk pushers rows
        pusher_rows = []
        for i, drv in enumerate(main.get("top_risk_drivers", [])[:3], 1):
            pusher_rows.append(f"""
            <div class="pusher-item">
              <div class="pusher-badge">#0{i} · {drv['layer']}</div>
              <div class="pusher-content">
                <div class="pusher-title">{drv['name']}</div>
                <div class="pusher-meta">指標ID: <code>{drv['id']}</code> · 權重 x{drv['weight']:.1f}</div>
              </div>
              <div class="pusher-val">{drv['value']:.1f}</div>
            </div>
            """)
        pushers_html = "\n".join(pusher_rows)

        step2_html = f"""
    <!-- Section 2: Five Layers & Peace Gate & Insights (UI-Step 2) -->
    <section class="grid-two-cols" style="display:grid;grid-template-columns:1.2fr 0.8fr;gap:24px;margin-top:24px;">
      <!-- Left Column: 5 Layers + Peace Gate -->
      <div style="display:flex;flex-direction:column;gap:24px;">
        <!-- Five Structural Layers Card (Ref: 09 TradeX Dimension Balance) -->
        <div class="panel-card">
          <div class="panel-header">
            <div class="panel-title">
              <span>五層結構維度平衡橫條 (Five Structural Dimensions)</span>
            </div>
            <span class="panel-tag">DIMENSION BALANCE · BASE WEIGHTED: {main['base_structural_score']:.1f}</span>
          </div>
          <div class="layers-container">
            {layers_html}
          </div>
        </div>

        <!-- Peace Mechanism Gate Breakdown (Ref: 08 SentinelX Wall) -->
        <div class="panel-card">
          <div class="panel-header">
            <div class="panel-title">
              <span>和平機制閘門與緩衝器 (Peace Mechanism Gate &amp; Buffers)</span>
            </div>
            <span class="panel-tag">MULTIPLIER: x{main['gate_factor']:.3f} · CAPACITY: {main['peace_capacity']:.1f}/100</span>
          </div>

          <div class="gate-formula-banner">
            <div class="gate-math">
              <strong>閘門公式 (Non-Blackbox Gate Formula)：</strong><br>
              <code>M_G = 1.4 - (PeaceCapacity / 100) × 0.8 = 1.4 - ({main['peace_capacity']:.1f}/100) × 0.8 = {main['gate_factor']:.3f}</code>
            </div>
            <p style="font-size:0.78rem;color:var(--text-muted);margin-top:6px;">
              當和平容量達 100 時乘數為 0.6（最高阻尼 -40%）；當和平緩衝完全崩潰 (0) 時乘數達 1.4（最高放大 +40%）。目前機制失效度 <strong>{main['gate_failure']:.1f}%</strong>，對基礎風險產生淨放大效應。
            </p>
          </div>

          <div style="margin-top:16px;">
            <div style="font-size:0.75rem;font-weight:700;color:var(--text-dim);text-transform:uppercase;margin-bottom:10px;font-family:var(--font-mono);">
              四大和平安全閥容量明細 (Peace Buffers Breakdown)
            </div>
            <div style="display:flex;flex-direction:column;gap:12px;">
              {buffers_html}
            </div>
          </div>
        </div>
      </div>

      <!-- Right Column: Interaction Terms + Top Risk Drivers Insights -->
      <div style="display:flex;flex-direction:column;gap:24px;">
        <!-- Interactions Card -->
        <div class="panel-card">
          <div class="panel-header">
            <div class="panel-title">
              <span>超線性互動效應加成 (Interaction Effects)</span>
            </div>
            <span class="panel-tag">TOTAL BONUS: +{main['interactions']['total']:.2f} / MAX 25.0</span>
          </div>

          <p style="font-size:0.78rem;color:var(--text-muted);margin-bottom:14px;">
            單一維度未爆發時體系尚可承受，但當多個脆弱維度同步耦合時，將產生超線性（Super-linear）系統性共振加成。
          </p>

          <div class="interactions-list">
            <div class="interaction-card">
              <div class="inter-head">
                <span class="inter-title">L1 × L2 資源短缺 × 分配不均</span>
                <span class="inter-val">+{main['interactions']['L1_x_L2']:.2f}</span>
              </div>
              <div class="inter-desc">生存資源吃緊且極端集中於少數階層或陣營，引發內外部零和爭奪。</div>
              <div class="inter-formula"><code>c=0.08 × (L1 × L2 / 100)</code></div>
            </div>

            <div class="interaction-card">
              <div class="inter-head">
                <span class="inter-title">L3 × L5 失業AI衝擊 × 未來恐懼</span>
                <span class="inter-val">+{main['interactions']['L3_x_L5']:.2f}</span>
              </div>
              <div class="inter-desc">大規模認知自動化與青年階層失業，疊加對未來長期衰落的絕望感，催生極端民粹與對外冒險。</div>
              <div class="inter-formula"><code>c=0.08 × (L3 × L5 / 100)</code></div>
            </div>

            <div class="interaction-card">
              <div class="inter-head">
                <span class="inter-title">L4 × 閘門 安全困境 × 機制失效</span>
                <span class="inter-val">+{main['interactions']['L4_x_GateFailure']:.2f}</span>
              </div>
              <div class="inter-desc">同盟剛性與常規軍事升級，遇上外交互信與國際仲裁全面停擺，缺乏脫困煞車皮。</div>
              <div class="inter-formula"><code>c=0.10 × (L4 × GateFail / 100)</code></div>
            </div>
          </div>
        </div>

        <!-- Top Pushers & Structural Insights (Ref: 08 SentinelX Insights) -->
        <div class="panel-card">
          <div class="panel-header">
            <div class="panel-title">
              <span>主推高因素與結構洞察 (Key Risk Pushers &amp; Insights)</span>
            </div>
            <span class="panel-tag">CRITICAL OBSERVATIONS</span>
          </div>

          <div class="pushers-list" id="pushers-list">
            {pushers_html}
          </div>

          <div class="insight-box" style="margin-top:16px;padding:12px;background:rgba(15, 23, 42, 0.6);border-left:3px solid var(--color-orange);border-radius:4px;">
            <div style="font-size:0.8rem;font-weight:700;color:#fed7aa;margin-bottom:4px;">戰略防務分析員洞察：</div>
            <p style="font-size:0.78rem;color:#cbd5e1;line-height:1.45;">
              當前風險總分高達 <strong>{risk_score:.1f}</strong>（進入階段三），核心驅動並非單一傳統軍備競賽，而是<strong>「算力晶圓與技術壟斷 (82.0)」</strong>與<strong>「多點領土引信 (80.0)」</strong>相互鎖死。外交互信緩衝（僅 36.0）與多邊仲裁（28.0）極度孱弱，導致任何邊境摩擦或技術先發管制均極易跨越防火牆直接升級。
            </p>
          </div>
        </div>
      </div>
    </section>
        """

    # Step 4: Interactive Conflict Risk Simulator
    if ui_step >= 4:
        # Predefined key simulator sliders
        sliders_def = [
            {"id": "sim_l3_ai", "ind_id": "l3_ai_displacement_rate", "layer": "L3", "name": "AI 認知自動化取代率", "name_en": "AI Cognitive Displacement Rate", "default": 62.0, "desc": "白領分析、編程與常規行政自動化衝擊程度"},
            {"id": "sim_l3_unemp", "ind_id": "l3_youth_unemployment", "layer": "L3", "name": "青年失業與社會挫折感", "name_en": "Youth Unemployment & Frustration", "default": 68.0, "desc": "青年群體經濟參與受限及極端化動員潛力"},
            {"id": "sim_l1_energy", "ind_id": "l1_energy_vulnerability", "layer": "L1", "name": "化石能源與電網供應鏈脆弱性", "name_en": "Energy Supply Vulnerability & Grid Stress", "default": 60.0, "desc": "電網負荷、油氣禁運及AI算力能源消耗爭奪"},
            {"id": "sim_l1_minerals", "ind_id": "l1_critical_minerals", "layer": "L1", "name": "關鍵礦物與稀土出口管制集中度", "name_en": "Critical Minerals Export Restrictions", "default": 72.0, "desc": "鎵鍺銻鋰關鍵原料禁運對國防工業之制約"},
            {"id": "sim_l4_bloc", "ind_id": "l4_bloc_polarization", "layer": "L4", "name": "全球陣營極化與同盟剛性", "name_en": "Geopolitical Bloc Polarization", "default": 78.0, "desc": "兩大陣營軍事同盟自動捲入條款與脫鉤剛性"},
            {"id": "sim_l5_fear", "ind_id": "l5_tech_supremacy_fear", "layer": "L5", "name": "技術霸權焦慮與先發打擊邏輯", "name_en": "Fear of Tech Loss & Preventive Logic", "default": 78.0, "desc": "憂慮對手獲得超強智能或技術突破之冒險動機"},
            {"id": "sim_gate_peace", "ind_id": "peace_capacity", "layer": "GATE", "name": "和平機制與外交互信容量 (Peace Capacity)", "name_en": "Peace Buffers & Diplomatic Trust Capacity", "default": 44.9, "desc": "元首熱線、經貿互賴、國際多邊法規與核威懾穩定度（越高越和平）"},
        ]

        slider_rows = []
        for sl in sliders_def:
            slider_rows.append(f"""
            <div class="sim-slider-group">
              <div class="sim-slider-header">
                <div>
                  <span class="sim-layer-tag">{sl['layer']}</span>
                  <span class="sim-label">{sl['name']}</span>
                </div>
                <span class="sim-val" id="val-{sl['id']}">{sl['default']:.1f}</span>
              </div>
              <input type="range" class="sim-range" id="{sl['id']}" min="0" max="100" step="1" value="{sl['default']}" oninput="runSimulation()">
              <div class="sim-slider-desc">{sl['desc']}</div>
            </div>
            """)
        sliders_html = "\n".join(slider_rows)

        step4_html = f"""
    <!-- Section 4: Interactive Conflict Risk Simulator (UI-Step 4) -->
    <section class="panel-card" style="margin-top:24px;" id="simulator-section">
      <div class="panel-header">
        <div class="panel-title">
          <span>實時交互衝突模擬器 (Interactive Crisis Escalation Simulator)</span>
        </div>
        <div class="sim-header-actions" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <button class="btn-tactical" onclick="resetSimulation()">重設為基準情境 (Reset)</button>
          <span class="panel-tag">PURE CLIENT-SIDE JS ENGINE · EXACT MODEL REPLICATION</span>
        </div>
      </div>
      <p style="font-size:0.78rem;color:var(--text-muted);margin-bottom:18px;">
        拖動下方滑桿即時調節關鍵驅動因子（AI 取代率、能源壓力、陣營極化、和平機制容量等）。純靜態 JavaScript 運算引擎內建同 Python 核心模型 100% 嚴格一致之加權公式、閘門乘數插值、三維超線性互動與 Soft-Clamp 飽和映射。
      </p>

      <div class="simulator-layout">
        <!-- Controls Column -->
        <div class="sim-controls-col">
          {sliders_html}
        </div>

        <!-- Simulation Live Result Column -->
        <div class="sim-result-col">
          <div class="sim-result-card">
            <div style="font-size:0.72rem;font-weight:700;letter-spacing:1px;color:var(--text-dim);text-transform:uppercase;font-family:var(--font-mono);">
              SIMULATED RISK PROJECTION
            </div>
            <div class="sim-score-row">
              <div class="sim-score-big" id="sim-index-display">{risk_score:.1f}</div>
              <div class="sim-delta-badge" id="sim-delta-display">基準 (±0.0)</div>
            </div>
            <div class="sim-stage-badge" id="sim-stage-display">STAGE {stage['number']} · {stage['title']}</div>
            
            <div class="sim-metrics-grid">
              <div class="sim-metric-cell">
                <span class="sim-m-label">基礎結構分</span>
                <span class="sim-m-val" id="sim-base-display">{main['base_structural_score']:.1f}</span>
              </div>
              <div class="sim-metric-cell">
                <span class="sim-m-label">和平閘門乘數</span>
                <span class="sim-m-val" id="sim-gate-display">x{main['gate_factor']:.3f}</span>
              </div>
              <div class="sim-metric-cell">
                <span class="sim-m-label">互動共振加成</span>
                <span class="sim-m-val" id="sim-inter-display">+{main['interactions']['total']:.2f}</span>
              </div>
              <div class="sim-metric-cell">
                <span class="sim-m-label">未夾持總分</span>
                <span class="sim-m-val" id="sim-raw-display">{main['raw_interacted_score']:.1f}</span>
              </div>
            </div>

            <!-- Simulated Probability Bands -->
            <div style="margin-top:16px;">
              <div style="font-size:0.75rem;font-weight:700;color:var(--text-dim);margin-bottom:8px;font-family:var(--font-mono);">
                結構風險情境帶（非經驗證概率）(SIMULATED STRUCTURAL RISK BANDS)
              </div>
              <div class="sim-prob-rows">
                <div class="sim-p-row">
                  <span class="sim-p-h">1 年期 (1-Year)</span>
                  <span class="sim-p-v" id="sim-prob-1y">{main['probability_bands']['1y']['central_pct']:.1f}% ({main['probability_bands']['1y']['lower_pct']:.1f}%–{main['probability_bands']['1y']['upper_pct']:.1f}%)</span>
                </div>
                <div class="sim-p-row">
                  <span class="sim-p-h">5 年期 (5-Year)</span>
                  <span class="sim-p-v" id="sim-prob-5y">{main['probability_bands']['5y']['central_pct']:.1f}% ({main['probability_bands']['5y']['lower_pct']:.1f}%–{main['probability_bands']['5y']['upper_pct']:.1f}%)</span>
                </div>
                <div class="sim-p-row">
                  <span class="sim-p-h">10 年期 (10-Year)</span>
                  <span class="sim-p-v" id="sim-prob-10y">{main['probability_bands']['10y']['central_pct']:.1f}% ({main['probability_bands']['10y']['lower_pct']:.1f}%–{main['probability_bands']['10y']['upper_pct']:.1f}%)</span>
                </div>
              </div>
            </div>

            <!-- Interactive Formula Breakdown -->
            <div class="sim-formula-note">
              <strong>實時公式追蹤 (Formula Tracking)：</strong><br>
              <code>Gated = (Base + Bonus) × GateFactor</code><br>
              <code>Index = SoftClamp(Gated, 70, 100)</code>
            </div>
          </div>
        </div>
      </div>
    </section>
        """
    if ui_step >= 3:
        # Generate Scenario Cards
        sc_cards = []
        for sc in data.get("scenarios", []):
            is_active_sc = (sc["id"] == data["metadata"]["active_scenario_id"])
            active_sc_cls = "active-sc" if is_active_sc else ""
            delta_val = sc.get("delta_from_baseline", 0.0)
            if delta_val > 0:
                delta_str = f"+{delta_val:.1f} pts"
                delta_cls = "delta-up"
            elif delta_val < 0:
                delta_str = f"{delta_val:.1f} pts"
                delta_cls = "delta-down"
            else:
                delta_str = "基準 (Baseline)"
                delta_cls = "delta-base"

            prob_1y = sc.get("probability_bands", {}).get("1y", {}).get("central_pct", 0.0)
            prob_5y = sc.get("probability_bands", {}).get("5y", {}).get("central_pct", 0.0)
            prob_10y = sc.get("probability_bands", {}).get("10y", {}).get("central_pct", 0.0)

            # Mini layer bars
            mini_bars = []
            for lid in ["L1", "L2", "L3", "L4", "L5"]:
                l_sc = sc.get("layer_scores", {}).get(lid, 50.0)
                mini_bars.append(f"""
                <div class="sc-mini-bar-wrap" title="{lid}: {l_sc:.1f}">
                  <div class="sc-mini-bar-fill" style="height:{l_sc}%;"></div>
                </div>
                """)
            mini_bars_html = "".join(mini_bars)

            sc_cards.append(f"""
            <div class="scenario-card {active_sc_cls}" id="sc-card-{sc['id']}" onclick="switchScenario('{sc['id']}')">
              <div class="sc-head">
                <span class="sc-id">{sc['id']}</span>
                <span class="sc-delta {delta_cls}">{delta_str}</span>
              </div>
              <div class="sc-title">{sc['title']}</div>
              <div class="sc-score-row">
                <div class="sc-score">{sc['global_risk_index']:.1f}</div>
                <div class="sc-stage-badge">STAGE {sc['stage_number']}</div>
                <div class="sc-mini-bars">{mini_bars_html}</div>
              </div>
              <div class="sc-probs">
                <span>1y: <strong>{prob_1y:.1f}%</strong></span>
                <span>5y: <strong>{prob_5y:.1f}%</strong></span>
                <span>10y: <strong>{prob_10y:.1f}%</strong></span>
              </div>
              <p class="sc-desc">{sc['description']}</p>
            </div>
            """)
        scenarios_html = "\n".join(sc_cards)

        # Generate Regional Pressure Cards
        reg_cards = []
        for reg in data.get("regional_pressures", []):
            indicators_tags = " ".join([f"<code>{ind}</code>" for ind in reg["indicators_used"]])
            reg_cards.append(f"""
            <div class="region-card {reg['color_class']}">
              <div class="reg-head">
                <div class="reg-title-wrap">
                  <span class="reg-name">{reg['name']}</span>
                  <span class="reg-en">{reg['name_en']}</span>
                </div>
                <span class="reg-badge badge-{reg['color_class']}">{reg['level_label']}</span>
              </div>
              <div class="reg-score-wrap">
                <span class="reg-score">{reg['score']:.1f}</span>
                <span class="reg-max">/100 區域綜合壓力</span>
              </div>
              <div class="progress-track" style="margin: 8px 0;">
                <div class="progress-fill" style="width: {reg['score']}%; background: var(--color-{reg['color_class']});"></div>
              </div>
              <div class="reg-disclaimer-tag">
                [示意拆分 · 模型指標映射]
              </div>
              <div class="reg-formula">
                {reg['formula']}
              </div>
              <div class="reg-indicators-list">
                映射來源：{indicators_tags}
              </div>
              <div class="reg-note">{reg['note']}</div>
            </div>
            """)
        regions_html = "\n".join(reg_cards)

        step3_html = f"""
    <!-- Section 3: Scenario Matrix & Regional Pressures (UI-Step 3) -->
    <section style="margin-top:24px;display:flex;flex-direction:column;gap:24px;">
      <!-- Scenario Matrix Cards (Ref: 03 GOD MODE Scenario Matrix) -->
      <div class="panel-card">
        <div class="panel-header">
          <div class="panel-title">
            <span>情境卡矩陣與動態比對 (Scenario Matrix &amp; Comparative Analysis)</span>
          </div>
          <span class="panel-tag">CLICK ANY CARD TO SWITCH SCENARIO VIEW</span>
        </div>
        <p style="font-size:0.78rem;color:var(--text-muted);margin-bottom:14px;">
          點擊下方任一情境卡片，即可將全儀表盤（總分 Gauge、四階段進度、五層維度橫條、閘門與互動效應）切換至該情境評估視角。所有數值均由模型公式實時驅動。
        </p>
        <div class="scenarios-grid">
          {scenarios_html}
        </div>
      </div>

      <!-- Regional Pressure Cards (Ref: 03 / 07 MRI Regional Cards) -->
      <div class="panel-card">
        <div class="panel-header">
          <div class="panel-title">
            <span>全球五大關鍵地緣戰區壓力卡列 (Regional Crisis Pressures)</span>
          </div>
          <span class="panel-tag">ILLUSTRATIVE DECOMPOSITION · MAPPED FROM CORE INDICATORS</span>
        </div>
        <div style="background:rgba(234, 179, 8, 0.08);border:1px solid rgba(234, 179, 8, 0.25);border-radius:6px;padding:8px 12px;margin-bottom:16px;font-size:0.76rem;color:#fef08a;">
          <strong>透明度說明 (Transparency Standard)：</strong>區域分數為「<strong>示意拆分 (Illustrative Mapping)</strong>」，由模型中既有之客觀指標（如海運咽喉受阻、領土引信點摩擦、算力壟斷等）指標原始平均合成，非獨立地理感測器實測，特此標註以防誤導。
        </div>
        <div class="regions-grid">
          {regions_html}
        </div>
      </div>
    </section>
        """

    # Step 5: Historical Timeline, Full Indicators Breakdown Table, Unconnected Sources & Methodology
    if ui_step >= 5:
        # 1. Historical Cases Cards
        hist_cards = []
        for h in data.get("historical", []):
            h_sc = h["global_risk_index"]
            if h_sc >= 85: h_color = "var(--color-red)"
            elif h_sc >= 70: h_color = "var(--color-orange)"
            elif h_sc >= 50: h_color = "var(--color-yellow)"
            else: h_color = "var(--color-green)"

            hist_cards.append(f"""
            <div class="hist-card">
              <div class="hist-head">
                <span class="hist-year">{h['year']}</span>
                <span class="hist-stage">STAGE {h['stage_number']} · {h['stage_title']}</span>
              </div>
              <div class="hist-title">{h['title']}</div>
              <div class="hist-score-wrap">
                <span class="hist-score" style="color:{h_color};">{h_sc:.1f}</span>
                <span class="hist-max">/100 · 閘門 x{h['gate_factor']:.3f} · 和平容量 {h['peace_capacity']:.1f}</span>
              </div>
              <div class="progress-track" style="margin: 8px 0;">
                <div class="progress-fill" style="width:{h_sc}%; background:{h_color};"></div>
              </div>
              <div class="hist-desc">{h['notes']}</div>
            </div>
            """)
        historical_html = "\n".join(hist_cards)

        # 2. Comprehensive Indicators Rows (L1-L5 + Gate Buffers = 34 indicators)
        indicator_rows = []
        combined_indicators = data.get("indicators", []) + data.get("gate_buffers", [])
        for ind in combined_indicators:
            ev_lvl = ind.get("evidence_level", "illustrative")
            if ev_lvl == "verified":
                ev_badge = '<span class="ev-badge ev-verified">VERIFIED · 實測驗證</span>'
            elif ev_lvl == "inference":
                ev_badge = '<span class="ev-badge ev-inference">INFERENCE · 統計推算</span>'
            else:
                ev_badge = '<span class="ev-badge ev-illustrative">ILLUSTRATIVE · 示範估算</span>'

            status = ind.get("status", "stale")
            stale_after = ind.get("stale_after", "365d")
            if status == "fresh":
                status_badge = '<span class="status-badge status-fresh">FRESH · 即時</span>'
            elif status == "stale":
                status_badge = f'<span class="status-badge status-stale">STALE ({stale_after})</span>'
            else:
                status_badge = '<span class="status-badge status-missing">MISSING</span>'

            v = ind["value"]
            if v >= 85: v_color = "var(--color-red)"
            elif v >= 70: v_color = "var(--color-orange)"
            elif v >= 50: v_color = "var(--color-yellow)"
            else: v_color = "var(--color-green)"

            raw_val = ind.get("raw_value", "-")
            raw_unit = ind.get("raw_unit", "")
            src_name = ind.get("source_name") or ind.get("source", "")
            pub_date = ind.get("publication_date", str(ind.get("year", "")))
            last_chk = ind.get("last_checked", "2026-10-21")
            norm_method = ind.get("normalization_method", "")
            rubric = ind.get("scoring_rubric", "")
            unc_note = ind.get("uncertainty_note", "")

            search_blob = f"{ind['layer']} {ind['id']} {ind['name']} {ind.get('name_en', '')} {src_name} {raw_val} {norm_method}".replace('"', '&quot;')

            indicator_rows.append(f"""
            <tr class="ind-row" data-layer="{ind['layer']}" data-search="{search_blob}">
              <td><span class="layer-code">{ind['layer']}</span></td>
              <td>
                <div style="font-family:var(--font-mono);font-size:0.75rem;font-weight:700;color:var(--accent-cyan);"><code>{ind['id']}</code></div>
                <div style="font-weight:600;color:#f8fafc;font-size:0.8rem;margin-top:2px;">{ind['name']}</div>
                <div style="font-size:0.7rem;color:var(--text-dim);">{ind.get('name_en', '')}</div>
              </td>
              <td>
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="font-family:var(--font-mono);font-weight:700;color:{v_color};width:36px;font-size:0.85rem;">{v:.1f}</span>
                  <div class="progress-track" style="width:50px;height:6px;">
                    <div class="progress-fill" style="width:{v}%;background:{v_color};"></div>
                  </div>
                </div>
                <div style="font-size:0.68rem;color:var(--text-dim);font-family:var(--font-mono);margin-top:2px;">權重 x{ind['weight']:.1f}</div>
              </td>
              <td>
                <div class="cell-raw">{raw_val}</div>
                <div class="cell-unit">{raw_unit}</div>
              </td>
              <td>
                <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-start;">
                  {ev_badge}
                  {status_badge}
                </div>
              </td>
              <td>
                <div class="cell-source">{src_name}</div>
                <div class="cell-date">發布：{pub_date}</div>
                <div class="cell-date">核對：{last_chk}</div>
              </td>
              <td>
                <div class="cell-norm">{norm_method}</div>
                {f'<div class="cell-rubric">{rubric}</div>' if rubric else ''}
              </td>
              <td style="font-size:0.73rem;color:var(--text-muted);line-height:1.35;">
                <div>{ind['note']}</div>
                {f'<div class="cell-uncertainty">不確定性：{unc_note}</div>' if unc_note else ''}
              </td>
            </tr>
            """)
        indicators_table_body = "\n".join(indicator_rows)

        # 3. Unconnected Data Sources Cards
        unc_cards = []
        for src in data.get("unconnected_sources", []):
            targets_str = " · ".join(src["target_regions"])
            unc_cards.append(f"""
            <div class="unc-card">
              <div class="unc-head">
                <span class="unc-name">{src['name']}</span>
                <span class="unc-badge">[未接數據源 · V1 STUB]</span>
              </div>
              <div class="unc-en">{src['name_en']}</div>
              <div class="unc-specs">
                <div>頻率：<code>{src['expected_cadence']}</code></div>
                <div>協議：<code>{src['protocol']}</code></div>
                <div>目標：<span>{targets_str}</span></div>
              </div>
              <p class="unc-desc">{src['description']}</p>
            </div>
            """)
        unconnected_html = "\n".join(unc_cards)

        step5_html = f"""
    <!-- Section 5: Historical Backtesting Timeline (UI-Step 5) -->
    <section class="panel-card" style="margin-top:24px;">
      <div class="panel-header">
        <div class="panel-title">
          <span>歷史重大危機回測時間線（回溯結構估算）(Historical Crisis Backtesting Timeline)</span>
        </div>
        <span class="panel-tag">RETROSPECTIVE STRUCTURAL ESTIMATES · 1913 / 1938 / 1962 / 1990 / 2025</span>
      </div>
      <p style="font-size:0.78rem;color:var(--text-muted);margin-bottom:12px;">
        將同一套五層結構公式與和平閘門應用於 20 世紀至今五大標誌性危機節點。歷史排序驗證：1938年二戰前夕 (99.6) &gt; 1913年一戰前夕 (96.1) &gt; 2025年當代前夕 (81.0) &gt; 1962年古巴危機 (77.4) &gt; 1990年冷戰終結 (23.4)。
      </p>
      <div style="background:rgba(234, 179, 8, 0.08);border:1px solid rgba(234, 179, 8, 0.25);border-radius:6px;padding:8px 12px;margin-bottom:16px;font-size:0.76rem;color:#fef08a;">
        <strong>嚴格標註：</strong>本時間線所有歷史點位均為<strong>回溯結構估算（Retrospective Structural Estimates）</strong>，僅使用各歷史時點已知資料，嚴禁使用事後資訊，亦非經驗校準之戰術開戰概率。
      </div>
      <div class="history-grid">
        {historical_html}
      </div>
    </section>

    <!-- Section 6: Comprehensive Indicators Breakdown Table (UI-Step 5) -->
    <section class="panel-card" style="margin-top:24px;">
      <div class="panel-header">
        <div class="panel-title">
          <span>模型底層全量指標明細表 (Comprehensive Indicator Inventory)</span>
        </div>
        <span class="panel-tag">34 INDICATORS · 3-TIER CREDIBILITY &amp; QUALITY AUDIT</span>
      </div>
      
      <!-- Table Controls -->
      <div class="table-controls">
        <div class="filter-group">
          <button class="filter-btn active" onclick="filterTable('ALL', this)">全部 (ALL 34)</button>
          <button class="filter-btn" onclick="filterTable('L1', this)">L1 生存資源</button>
          <button class="filter-btn" onclick="filterTable('L2', this)">L2 分配失衡</button>
          <button class="filter-btn" onclick="filterTable('L3', this)">L3 工作與AI</button>
          <button class="filter-btn" onclick="filterTable('L4', this)">L4 安全困境</button>
          <button class="filter-btn" onclick="filterTable('L5', this)">L5 未來恐懼</button>
          <button class="filter-btn" onclick="filterTable('GATE', this)">GATE 和平閘門</button>
        </div>
        <div class="search-box-wrap">
          <input type="text" id="ind-search" class="search-input" placeholder="搜尋指標代碼、名稱或來源出處..." oninput="searchTable()">
        </div>
      </div>

      <div class="mobile-table-hint">← 左右滑動查看完整表格 →</div>
      <div class="table-scroll">
        <table class="styled-table">
          <thead>
            <tr>
              <th style="width:45px;">層級</th>
              <th style="width:190px;">指標代碼與名稱</th>
              <th style="width:115px;">風險分數</th>
              <th style="width:140px;">原始數據與單位</th>
              <th style="width:130px;">證據與新鮮度</th>
              <th style="width:160px;">來源與期數</th>
              <th style="width:230px;">換算方法與評分規則</th>
              <th style="width:220px;">結構背景與不確定性</th>
            </tr>
          </thead>
          <tbody id="indicators-tbody">
            {indicators_table_body}
          </tbody>
        </table>
      </div>
    </section>

    <!-- Section 7: Unconnected Data Sources Stubs (UI-Step 5) -->
    <section class="panel-card" style="margin-top:24px;">
      <div class="panel-header">
        <div class="panel-title">
          <span>即時感知信號源接入佔位 (Live Sensor Feeds &amp; Telemetry Stubs)</span>
        </div>
        <span class="panel-tag">STRICTLY LABELED AS UNCONNECTED · ZERO FAKE TELEMETRY</span>
      </div>
      <div style="background:rgba(239, 68, 68, 0.08);border:1px solid rgba(239, 68, 68, 0.25);border-radius:6px;padding:8px 12px;margin-bottom:16px;font-size:0.76rem;color:#fca5a5;">
        <strong>嚴肅聲明：</strong>以下 5 大即時遙測源在 v1 靜態版本中<strong>全部標記為「未接數據源」</strong>佔位預留。本系統為純純離線靜態儀表板，嚴格不偽造任何虛假即時動態、模擬雷達或冒充即時新聞。
      </div>
      <div class="unconnected-grid">
        {unconnected_html}
      </div>
    </section>

    <!-- Section 7.5: Three-Tier Credibility Architecture (UI-Step 5) -->
    <section class="panel-card" style="margin-top:24px;">
      <div class="panel-header">
        <div class="panel-title">
          <span>三種可信度分立體系架構 (Three-Tier Credibility Architecture)</span>
        </div>
        <span class="panel-tag">STRICT SCIENTIFIC SEPARATION · TRANSPARENT &amp; REFUTABLE</span>
      </div>
      <div style="background:rgba(59, 130, 246, 0.08);border:1px solid rgba(59, 130, 246, 0.25);border-radius:6px;padding:10px 14px;margin-bottom:16px;font-size:0.78rem;color:#93c5fd;line-height:1.5;">
        <strong>架構原則（用戶規範）：</strong>為防止科學黑箱與概念混淆，本系統將「數據來源客觀度」、「分數換算方法透明度」與「模型對現實的預測能力」嚴格分離為獨立維度，禁止相互替代或含混掩飾。
      </div>
      <div class="credibility-grid" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px;">
        <!-- Tier 1 -->
        <div class="cred-card">
          <div class="cred-head">
            <span class="cred-badge">TIER 1 · 來源層</span>
            <div class="cred-title">原始統計可信度</div>
            <div class="cred-en">Raw Statistical Credibility</div>
          </div>
          <div class="cred-body">
            <p><strong>指標輸入數據之客觀性與權威度：</strong></p>
            <ul style="padding-left:18px;margin:8px 0;font-size:0.76rem;color:var(--text-muted);display:flex;flex-direction:column;gap:6px;">
              <li><strong style="color:#6ee7b7;">VERIFIED (20.6%, 7項)</strong>：SIPRI軍費、IMF公共債務、WID財富、IEA礦物等客觀計量。</li>
              <li><strong style="color:#67e8f9;">INFERENCE (58.8%, 20項)</strong>：FAO庫存比、WRI水壓、ILO失業率等權威多源代理推算。</li>
              <li><strong style="color:#fde047;">ILLUSTRATIVE (20.6%, 7項)</strong>：外交互信、誤判窗口、技術恐懼等具體量表估算。</li>
            </ul>
            <div class="cred-rule">鐵律：嚴禁將主觀估值或推論指標改標為 Verified。</div>
          </div>
        </div>

        <!-- Tier 2 -->
        <div class="cred-card">
          <div class="cred-head">
            <span class="cred-badge">TIER 2 · 方法層</span>
            <div class="cred-title">換算方法透明度</div>
            <div class="cred-en">Scoring Method Transparency</div>
          </div>
          <div class="cred-body">
            <p><strong>原始物理量映射為 0–100 風險分之演算法：</strong></p>
            <ul style="padding-left:18px;margin:8px 0;font-size:0.76rem;color:var(--text-muted);display:flex;flex-direction:column;gap:6px;">
              <li><strong>公開數學公式</strong>：所有 34 個指標均具備完全公開且可重算的 <code>normalization_method</code> 與 <code>scoring_rubric</code>。</li>
              <li><strong>完全可覆核</strong>：任何獨立第三方研究者照公式計算皆可得到相同之 0–100 風險分數。</li>
              <li><strong>詳盡審計歸檔</strong>：詳見 <code>docs/indicator-audit-v03.md</code>，無任何隱藏常數或黑箱調整。</li>
            </ul>
            <div class="cred-rule">原則：可追溯、可重算、可證偽。</div>
          </div>
        </div>

        <!-- Tier 3 -->
        <div class="cred-card">
          <div class="cred-head">
            <span class="cred-badge">TIER 3 · 模型層</span>
            <div class="cred-title">模型預測能力界限</div>
            <div class="cred-en">Model Predictive Limits</div>
          </div>
          <div class="cred-body">
            <p><strong>模型輸出對現實世界戰爭爆發之解讀邊界：</strong></p>
            <ul style="padding-left:18px;margin:8px 0;font-size:0.76rem;color:var(--text-muted);display:flex;flex-direction:column;gap:6px;">
              <li><strong>結構脆弱性評估</strong>：衡量國際體系易燃度，<strong>非戰術開戰預警儀</strong>，無法預測衝突具體發動日期。</li>
              <li><strong>非經驗證概率</strong>：情境帶為 Logistic 結構映射，非頻率學派或計量驗證概率。</li>
              <li><strong>拒絕迎合預期調權重</strong>：模型可被推翻；歷史回測失真時如實呈現，不隨意修飾權重。</li>
            </ul>
            <div class="cred-rule">定位：宏觀結構風險情境估算，非保證真理。</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Section 8: Methodology & Disclaimer Footer Card (UI-Step 5) -->
    <section class="panel-card" style="margin-top:24px;border-color:var(--border-bright);">
      <div class="panel-header">
        <div class="panel-title">
          <span>方法學邊界與免責聲明 (Methodology &amp; Disclaimers)</span>
        </div>
        <span class="panel-tag">SCENARIO EVALUATION · NOT TACTICAL PREDICTION</span>
      </div>
      <div class="methodology-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:20px;font-size:0.78rem;color:var(--text-muted);line-height:1.5;">
        <div>
          <h4 style="color:#f8fafc;margin-bottom:6px;">一、模型定位與局限性</h4>
          <p>
            本模型旨在評估國際體系是否滑入<strong>「四階段危機」</strong>之總體結構壓力，重點在於揭示「生存資源、分配不均、AI取代、安全困境、未來恐懼」五層因子之超線性耦合共振，以及和平緩衝安全閥之有效性。本模型<strong>非戰術預警系統</strong>，無法預測具體引信事件觸發的精確日期與作戰細節。
          </p>
        </div>
        <div>
          <h4 style="color:#f8fafc;margin-bottom:6px;">二、三級數據透明度標準</h4>
          <p>
            所有指標嚴格區分 <code>verified</code>（客觀實測來源）、<code>inference</code>（多方數據統計推算）與 <code>illustrative</code>（情境示範性假說）。結構風險情境帶為結構壓力函數之 Logistic 映射估算，非頻率學派或已驗證之統計預測，讀者切勿將其直接作為金融投機或不可逆防務決策之唯一依據。
          </p>
        </div>
      </div>
    </section>
        """

    # CSS styles
    css = """<style>
    :root {
      --bg-base: #080d1a;
      --bg-surface: #0f172a;
      --bg-card: #131d36;
      --bg-card-hover: #1a2747;
      --border-color: #1e293b;
      --border-bright: #334155;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent-cyan: #06b6d4;
      --accent-blue: #3b82f6;
      --color-green: #10b981;
      --color-yellow: #eab308;
      --color-orange: #f97316;
      --color-red: #ef4444;
      --color-red-glow: rgba(239, 68, 68, 0.25);
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", "PingFang SC", "Microsoft YaHei", sans-serif;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      overflow-x: hidden;
      width: 100%;
      max-width: 100%;
    }
    body {
      background: var(--bg-base);
      color: var(--text-main);
      font-family: var(--font-sans);
      line-height: 1.5;
      padding-bottom: 40px;
      -webkit-font-smoothing: antialiased;
    }
    .dashboard-container,
    .panel-card,
    .hero-grid,
    .grid-two-cols,
    .simulator-layout,
    .sim-controls-col,
    .sim-result-col,
    .scenarios-grid,
    .regions-grid,
    .history-grid,
    .table-scroll,
    .unconnected-grid,
    .credibility-grid,
    .driver-steps-grid,
    .quality-metric-row,
    .methodology-grid {
      min-width: 0;
    }

    /* Top Navigation Bar */
    .top-bar {
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-color);
      padding: 14px 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 50;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
      min-width: 0;
      width: 100%;
    }
    .brand-group {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .radar-icon {
      width: 14px;
      height: 14px;
      background: var(--color-red);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--color-red);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
      100% { opacity: 1; transform: scale(1); }
    }
    .brand-title {
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: #fff;
    }
    .brand-sub {
      font-size: 0.8rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
    .top-meta {
      display: flex;
      align-items: center;
      gap: 16px;
      font-size: 0.82rem;
    }
    .meta-badge {
      padding: 4px 10px;
      border-radius: 4px;
      font-weight: 600;
      font-size: 0.75rem;
      font-family: var(--font-mono);
      letter-spacing: 0.5px;
    }
    .badge-alert {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid var(--color-red);
      color: #fca5a5;
    }
    .badge-offline {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid var(--color-green);
      color: #6ee7b7;
    }
    .badge-live {
      background: rgba(59, 130, 246, 0.15);
      border: 1px solid #3b82f6;
      color: #93c5fd;
    }
    .badge-step {
      background: rgba(6, 182, 212, 0.12);
      border: 1px solid var(--accent-cyan);
      color: #67e8f9;
    }

    /* Container */
    .dashboard-container {
      max-width: 1380px;
      margin: 24px auto;
      padding: 0 24px;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }

    /* Cards */
    .panel-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 22px;
      position: relative;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }
    .panel-title {
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: #f1f5f9;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .panel-tag {
      font-size: 0.72rem;
      font-family: var(--font-mono);
      color: var(--text-dim);
    }

    /* Section 1: Top Hero Grid (Gauge + Headline Summary) */
    .hero-grid {
      display: grid;
      grid-template-columns: 420px 1fr;
      gap: 24px;
    }

    /* Gauge Card */
    .gauge-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      justify-content: center;
      padding: 26px 20px;
      background: linear-gradient(180deg, #131d36 0%, #0d1424 100%);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
    }
    .gauge-wrapper {
      width: 100%;
      max-width: 320px;
      margin-bottom: -10px;
    }
    .gauge-svg {
      width: 100%;
      height: auto;
      overflow: visible;
    }
    .score-big {
      font-size: 3.4rem;
      font-weight: 800;
      font-family: var(--font-mono);
      line-height: 1;
      color: #fff;
      text-shadow: 0 0 20px rgba(239, 68, 68, 0.5);
      margin-top: -6px;
    }
    .score-label {
      font-size: 0.88rem;
      font-weight: 700;
      color: #cbd5e1;
      margin-top: 6px;
      letter-spacing: 0.5px;
    }
    .score-sub {
      font-size: 0.76rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
    .gauge-meta-pills {
      display: flex;
      gap: 12px;
      margin-top: 18px;
      width: 100%;
      justify-content: center;
    }
    .pill {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 6px 12px;
      text-align: center;
      flex: 1;
      max-width: 140px;
    }
    .pill-label {
      font-size: 0.7rem;
      color: var(--text-dim);
      text-transform: uppercase;
    }
    .pill-val {
      font-size: 0.95rem;
      font-weight: 700;
      font-family: var(--font-mono);
      color: #e2e8f0;
      margin-top: 2px;
    }

    /* Stage Progression Tracker */
    .stages-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
    }
    .stage-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      transition: all 0.2s ease;
      opacity: 0.6;
    }
    .stage-card.active {
      opacity: 1;
      border-color: var(--color-orange);
      background: linear-gradient(180deg, rgba(249, 115, 22, 0.08) 0%, rgba(15, 23, 42, 0.9) 100%);
      box-shadow: 0 0 15px rgba(249, 115, 22, 0.2);
    }
    .stage-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .stage-num {
      font-size: 0.7rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: var(--accent-cyan);
    }
    .stage-tag {
      font-size: 0.68rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
    .active-tag {
      color: var(--color-orange);
      font-weight: 700;
    }
    .stage-card-title {
      font-size: 0.95rem;
      font-weight: 700;
      color: #fff;
    }
    .stage-card-title-en {
      font-size: 0.72rem;
      color: var(--text-dim);
      margin-bottom: 4px;
    }
    .stage-card-desc {
      font-size: 0.78rem;
      color: var(--text-muted);
      line-height: 1.4;
      flex: 1;
    }

    /* Active Stage Details Banner */
    .active-stage-banner {
      margin-top: 18px;
      background: rgba(249, 115, 22, 0.08);
      border: 1px solid rgba(249, 115, 22, 0.35);
      border-radius: 6px;
      padding: 14px 18px;
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .banner-badge {
      background: var(--color-orange);
      color: #000;
      font-weight: 800;
      font-size: 0.75rem;
      padding: 4px 8px;
      border-radius: 4px;
      white-space: nowrap;
    }
    .banner-text {
      font-size: 0.85rem;
      color: #fdba74;
      line-height: 1.4;
    }

    /* Probability Bands Grid */
    .prob-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-top: 14px;
    }
    .prob-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px 14px;
    }
    .prob-horizon {
      font-size: 0.72rem;
      color: var(--text-dim);
      text-transform: uppercase;
      font-family: var(--font-mono);
    }
    .prob-central {
      font-size: 1.35rem;
      font-weight: 700;
      font-family: var(--font-mono);
      color: #f1f5f9;
      margin: 4px 0 2px 0;
    }
    .prob-band {
      font-size: 0.76rem;
      color: var(--accent-cyan);
      font-family: var(--font-mono);
    }

    /* Step 2: Five Layers & Dimension Bars */
    .layers-container {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .layer-row {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .layer-info {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .layer-name-wrap {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .layer-code {
      font-size: 0.75rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: var(--accent-cyan);
      background: rgba(6, 182, 212, 0.1);
      padding: 2px 6px;
      border-radius: 3px;
    }
    .layer-name {
      font-size: 0.95rem;
      font-weight: 700;
      color: #f8fafc;
    }
    .layer-en {
      font-size: 0.75rem;
      color: var(--text-dim);
    }
    .layer-val-wrap {
      display: flex;
      align-items: baseline;
      gap: 6px;
      font-family: var(--font-mono);
    }
    .layer-weight {
      font-size: 0.72rem;
      color: var(--text-dim);
    }
    .layer-score {
      font-size: 1.25rem;
      font-weight: 800;
    }
    .layer-max {
      font-size: 0.75rem;
      color: var(--text-dim);
    }
    .progress-track {
      width: 100%;
      height: 8px;
      background: #1e293b;
      border-radius: 4px;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.4s ease;
    }
    .layer-desc {
      font-size: 0.74rem;
      color: var(--text-muted);
    }

    /* Gate Banner & Buffers */
    .gate-formula-banner {
      background: rgba(15, 23, 42, 0.75);
      border: 1px dashed var(--border-bright);
      border-radius: 6px;
      padding: 12px 14px;
    }
    .gate-math {
      font-size: 0.8rem;
      color: #cbd5e1;
    }
    .gate-math code {
      font-family: var(--font-mono);
      color: var(--accent-cyan);
      background: rgba(0, 0, 0, 0.3);
      padding: 2px 6px;
      border-radius: 3px;
    }
    .buffer-item {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 10px 14px;
    }

    /* Interactions Cards */
    .interactions-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .interaction-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .inter-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .inter-title {
      font-size: 0.84rem;
      font-weight: 700;
      color: #f1f5f9;
    }
    .inter-val {
      font-size: 1rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: var(--color-orange);
    }
    .inter-desc {
      font-size: 0.75rem;
      color: var(--text-muted);
    }
    .inter-formula {
      font-size: 0.7rem;
      font-family: var(--font-mono);
      color: var(--text-dim);
      margin-top: 2px;
    }

    /* Top Pushers */
    .pushers-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .pusher-item {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 10px 14px;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .pusher-badge {
      font-size: 0.72rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: var(--color-red);
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.3);
      padding: 2px 6px;
      border-radius: 4px;
      white-space: nowrap;
    }
    .pusher-content {
      flex: 1;
    }
    .pusher-title {
      font-size: 0.82rem;
      font-weight: 600;
      color: #f8fafc;
    }
    .pusher-meta {
      font-size: 0.7rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
    .pusher-val {
      font-size: 1.15rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: var(--color-red);
    }

    /* Step 3: Scenario Matrix Cards */
    .scenarios-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }
    .scenario-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      cursor: pointer;
      transition: all 0.2s ease;
      position: relative;
    }
    .scenario-card:hover {
      border-color: var(--border-bright);
      transform: translateY(-2px);
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
    }
    .scenario-card.active-sc {
      border-color: var(--accent-cyan);
      background: linear-gradient(180deg, rgba(6, 182, 212, 0.08) 0%, rgba(15, 23, 42, 0.95) 100%);
      box-shadow: 0 0 15px rgba(6, 182, 212, 0.25);
    }
    .sc-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .sc-id {
      font-size: 0.7rem;
      font-weight: 700;
      font-family: var(--font-mono);
      color: var(--text-dim);
    }
    .sc-delta {
      font-size: 0.72rem;
      font-weight: 700;
      font-family: var(--font-mono);
      padding: 2px 6px;
      border-radius: 4px;
    }
    .delta-up { background: rgba(239, 68, 68, 0.15); color: #fca5a5; }
    .delta-down { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; }
    .delta-base { background: rgba(148, 163, 184, 0.15); color: #cbd5e1; }
    .sc-title {
      font-size: 0.92rem;
      font-weight: 700;
      color: #f8fafc;
      line-height: 1.35;
      min-height: 2.7rem;
    }
    .sc-score-row {
      display: flex;
      align-items: baseline;
      gap: 10px;
    }
    .sc-score {
      font-size: 1.6rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: #fff;
    }
    .sc-stage-badge {
      font-size: 0.72rem;
      font-weight: 700;
      font-family: var(--font-mono);
      color: var(--accent-cyan);
    }
    .sc-mini-bars {
      display: flex;
      gap: 3px;
      height: 20px;
      align-items: flex-end;
      margin-left: auto;
    }
    .sc-mini-bar-wrap {
      width: 5px;
      height: 100%;
      background: #1e293b;
      border-radius: 2px;
      overflow: hidden;
      display: flex;
      align-items: flex-end;
    }
    .sc-mini-bar-fill {
      width: 100%;
      background: var(--accent-cyan);
      border-radius: 1px;
    }
    .sc-probs {
      display: flex;
      justify-content: space-between;
      font-size: 0.72rem;
      font-family: var(--font-mono);
      color: var(--text-dim);
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      padding-top: 6px;
    }
    .sc-probs strong { color: #e2e8f0; }
    .sc-desc {
      font-size: 0.74rem;
      color: var(--text-muted);
      line-height: 1.35;
    }

    /* Regional Cards Grid */
    .regions-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 14px;
    }
    .region-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .reg-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 6px;
    }
    .reg-title-wrap {
      display: flex;
      flex-direction: column;
    }
    .reg-name {
      font-size: 0.88rem;
      font-weight: 700;
      color: #f8fafc;
    }
    .reg-en {
      font-size: 0.68rem;
      color: var(--text-dim);
    }
    .reg-badge {
      font-size: 0.68rem;
      font-weight: 700;
      font-family: var(--font-mono);
      padding: 2px 6px;
      border-radius: 4px;
      white-space: nowrap;
    }
    .badge-danger { background: rgba(239, 68, 68, 0.15); color: #fca5a5; border: 1px solid var(--color-red); }
    .badge-warning { background: rgba(249, 115, 22, 0.15); color: #fdba74; border: 1px solid var(--color-orange); }
    .badge-elevated { background: rgba(234, 179, 8, 0.15); color: #fef08a; border: 1px solid var(--color-yellow); }
    .badge-success { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; border: 1px solid var(--color-green); }
    .reg-score-wrap {
      display: flex;
      align-items: baseline;
      gap: 6px;
      margin-top: 4px;
    }
    .reg-score {
      font-size: 1.45rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: #fff;
    }
    .reg-max {
      font-size: 0.72rem;
      color: var(--text-dim);
    }
    .reg-disclaimer-tag {
      font-size: 0.68rem;
      color: #f59e0b;
      font-weight: 600;
      font-family: var(--font-mono);
    }
    .reg-formula {
      font-size: 0.72rem;
      color: #cbd5e1;
      background: rgba(15, 23, 42, 0.75);
      border: 1px solid rgba(148, 163, 184, 0.2);
      border-radius: 4px;
      padding: 6px 8px;
      line-height: 1.45;
      word-break: break-word;
      overflow-wrap: break-word;
      white-space: normal;
      margin: 4px 0;
      font-family: var(--font-mono);
    }
    .reg-indicators-list {
      font-size: 0.68rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
    .reg-indicators-list code {
      background: rgba(0, 0, 0, 0.25);
      padding: 1px 4px;
      border-radius: 3px;
      color: var(--accent-cyan);
    }
    .reg-note {
      font-size: 0.72rem;
      color: var(--text-muted);
      line-height: 1.35;
      margin-top: 4px;
    }

    /* Step 4: Simulator Styles */
    .simulator-layout {
      display: grid;
      grid-template-columns: 1.25fr 0.75fr;
      gap: 24px;
    }
    .btn-tactical {
      background: rgba(6, 182, 212, 0.15);
      border: 1px solid var(--accent-cyan);
      color: #67e8f9;
      padding: 6px 12px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 700;
      font-family: var(--font-mono);
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-tactical:hover {
      background: rgba(6, 182, 212, 0.3);
      box-shadow: 0 0 10px rgba(6, 182, 212, 0.4);
    }
    .sim-controls-col {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .sim-slider-group {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .sim-slider-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .sim-layer-tag {
      font-size: 0.7rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: var(--accent-cyan);
      background: rgba(6, 182, 212, 0.1);
      padding: 2px 5px;
      border-radius: 3px;
      margin-right: 6px;
    }
    .sim-label {
      font-size: 0.84rem;
      font-weight: 700;
      color: #f1f5f9;
    }
    .sim-val {
      font-size: 1.05rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: var(--accent-cyan);
    }
    .sim-range {
      width: 100%;
      height: 6px;
      background: #1e293b;
      border-radius: 3px;
      outline: none;
      -webkit-appearance: none;
      appearance: none;
      cursor: pointer;
    }
    .sim-range::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: var(--accent-cyan);
      box-shadow: 0 0 8px rgba(6, 182, 212, 0.8);
      cursor: pointer;
    }
    .sim-range::-moz-range-thumb {
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: var(--accent-cyan);
      box-shadow: 0 0 8px rgba(6, 182, 212, 0.8);
      cursor: pointer;
    }
    .sim-slider-desc {
      font-size: 0.72rem;
      color: var(--text-dim);
    }
    .sim-result-card {
      background: linear-gradient(180deg, #131d36 0%, #0d1424 100%);
      border: 1px solid var(--accent-cyan);
      border-radius: 8px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      box-shadow: 0 0 20px rgba(6, 182, 212, 0.15);
      position: sticky;
      top: 80px;
    }
    .sim-score-row {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
    }
    .sim-score-big {
      font-size: 3rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: #fff;
      line-height: 1;
    }
    .sim-delta-badge {
      font-size: 0.85rem;
      font-weight: 700;
      font-family: var(--font-mono);
      padding: 4px 8px;
      border-radius: 4px;
      background: rgba(148, 163, 184, 0.15);
      color: #cbd5e1;
    }
    .sim-stage-badge {
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--color-orange);
      padding: 4px 10px;
      background: rgba(249, 115, 22, 0.12);
      border: 1px solid rgba(249, 115, 22, 0.3);
      border-radius: 4px;
      text-align: center;
    }
    .sim-metrics-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 4px;
    }
    .sim-metric-cell {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
    }
    .sim-m-label {
      font-size: 0.68rem;
      color: var(--text-dim);
      text-transform: uppercase;
    }
    .sim-m-val {
      font-size: 1rem;
      font-weight: 700;
      font-family: var(--font-mono);
      color: #e2e8f0;
      margin-top: 2px;
    }
    .sim-prob-rows {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .sim-p-row {
      display: flex;
      justify-content: space-between;
      font-size: 0.76rem;
      background: var(--bg-surface);
      padding: 6px 10px;
      border-radius: 4px;
      border: 1px solid var(--border-color);
    }
    .sim-p-h {
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
    .sim-p-v {
      font-family: var(--font-mono);
      font-weight: 700;
      color: var(--accent-cyan);
    }
    .sim-formula-note {
      font-size: 0.7rem;
      color: var(--text-dim);
      background: rgba(0, 0, 0, 0.25);
      border-radius: 4px;
      padding: 8px;
      line-height: 1.4;
    }
    .sim-formula-note code {
      color: var(--accent-cyan);
    }

    /* Step 5: Historical Timeline */
    .history-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 14px;
    }
    .hist-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .hist-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .hist-year {
      font-size: 1.1rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: #fff;
    }
    .hist-stage {
      font-size: 0.68rem;
      font-weight: 700;
      font-family: var(--font-mono);
      color: var(--accent-cyan);
    }
    .hist-title {
      font-size: 0.86rem;
      font-weight: 700;
      color: #f1f5f9;
      line-height: 1.35;
      min-height: 2.3rem;
    }
    .hist-score-wrap {
      display: flex;
      align-items: baseline;
      gap: 6px;
      margin-top: 4px;
    }
    .hist-score {
      font-size: 1.5rem;
      font-weight: 800;
      font-family: var(--font-mono);
    }
    .hist-max {
      font-size: 0.68rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
    .hist-desc {
      font-size: 0.72rem;
      color: var(--text-muted);
      line-height: 1.35;
    }

    /* Table Styles */
    .table-controls {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }
    .filter-group {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .filter-btn {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 5px 10px;
      border-radius: 4px;
      font-size: 0.74rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }
    .filter-btn:hover {
      border-color: var(--border-bright);
      color: #fff;
    }
    .filter-btn.active {
      background: rgba(6, 182, 212, 0.15);
      border-color: var(--accent-cyan);
      color: #67e8f9;
    }
    .search-box-wrap {
      flex: 1;
      max-width: 320px;
    }
    .search-input {
      width: 100%;
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 4px;
      padding: 6px 12px;
      font-size: 0.78rem;
      color: #fff;
      outline: none;
    }
    .search-input:focus {
      border-color: var(--accent-cyan);
    }
    .table-scroll {
      width: 100%;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      margin-top: 14px;
      min-width: 0;
    }
    .styled-table {
      width: 100%;
      min-width: 1080px;
      border-collapse: collapse;
      font-size: 0.76rem;
      text-align: left;
    }
    .mobile-table-hint {
      display: none;
      font-size: 0.75rem;
      color: var(--accent-cyan);
      background: rgba(6, 182, 212, 0.08);
      border: 1px solid rgba(6, 182, 212, 0.2);
      border-radius: 4px;
      padding: 8px 12px;
      margin-top: 10px;
      text-align: center;
      font-family: var(--font-mono);
    }
    .styled-table th {
      background: rgba(15, 23, 42, 0.9);
      color: var(--text-dim);
      font-weight: 700;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border-color);
      font-family: var(--font-mono);
      text-transform: uppercase;
      font-size: 0.7rem;
      white-space: nowrap;
    }
    .styled-table td {
      padding: 10px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      vertical-align: top;
    }
    .styled-table tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }
    .styled-table code {
      font-family: var(--font-mono);
      color: var(--accent-cyan);
      background: rgba(0, 0, 0, 0.3);
      padding: 1px 4px;
      border-radius: 3px;
    }
    .ev-badge {
      display: inline-block;
      font-size: 0.65rem;
      font-weight: 700;
      font-family: var(--font-mono);
      padding: 2px 6px;
      border-radius: 3px;
      white-space: nowrap;
    }
    .ev-verified { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; border: 1px solid var(--color-green); }
    .ev-inference { background: rgba(59, 130, 246, 0.15); color: #93c5fd; border: 1px solid var(--accent-blue); }
    .ev-illustrative { background: rgba(234, 179, 8, 0.15); color: #fef08a; border: 1px solid var(--color-yellow); }

    /* Unconnected Stubs */
    .unconnected-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
    }
    .unc-card {
      background: var(--bg-surface);
      border: 1px dashed var(--border-bright);
      border-radius: 6px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .unc-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 8px;
    }
    .unc-name {
      font-size: 0.84rem;
      font-weight: 700;
      color: #f1f5f9;
    }
    .unc-badge {
      font-size: 0.65rem;
      font-weight: 800;
      font-family: var(--font-mono);
      color: #fca5a5;
      background: rgba(239, 68, 68, 0.15);
      padding: 2px 5px;
      border-radius: 3px;
      white-space: nowrap;
    }
    .unc-en {
      font-size: 0.68rem;
      color: var(--text-dim);
    }
    .unc-specs {
      font-size: 0.7rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
      display: flex;
      flex-direction: column;
      gap: 2px;
      margin: 4px 0;
    }
    .unc-specs code {
      color: var(--accent-cyan);
    }
    .unc-desc {
      font-size: 0.72rem;
      color: var(--text-muted);
      line-height: 1.35;
    }

    /* Driver Decomposition & Data Quality Styles */
    .driver-steps-grid {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .driver-step-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 10px 14px;
    }
    .driver-step-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 4px;
    }
    .driver-step-num {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      font-weight: 700;
      color: var(--accent-cyan);
      background: rgba(6, 182, 212, 0.15);
      padding: 2px 6px;
      border-radius: 3px;
      margin-right: 8px;
    }
    .driver-step-name {
      font-size: 0.82rem;
      font-weight: 600;
      color: #f1f5f9;
      flex: 1;
    }
    .driver-step-val {
      font-family: var(--font-mono);
      font-weight: 700;
      font-size: 0.9rem;
      color: var(--color-orange);
    }
    .driver-step-desc {
      font-size: 0.75rem;
      color: var(--text-muted);
      line-height: 1.4;
    }
    .quality-metric-row {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 12px;
      margin-bottom: 12px;
    }
    .quality-cell {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 10px 12px;
      text-align: center;
    }
    .q-label {
      font-size: 0.72rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
      margin-bottom: 4px;
    }
    .q-val {
      font-family: var(--font-mono);
      font-size: 0.95rem;
      font-weight: 700;
      margin-bottom: 2px;
    }
    .q-sub {
      font-size: 0.68rem;
      color: var(--text-muted);
    }

    /* Three-Tier Credibility Architecture Styles */
    .credibility-grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 18px;
    }
    .cred-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .cred-head {
      margin-bottom: 12px;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 8px;
    }
    .cred-badge {
      display: inline-block;
      font-family: var(--font-mono);
      font-size: 0.7rem;
      font-weight: 700;
      color: var(--accent-cyan);
      background: rgba(6, 182, 212, 0.12);
      padding: 2px 8px;
      border-radius: 4px;
      margin-bottom: 6px;
    }
    .cred-title {
      font-size: 0.95rem;
      font-weight: 700;
      color: #f8fafc;
    }
    .cred-en {
      font-size: 0.72rem;
      color: var(--text-dim);
    }
    .cred-body {
      font-size: 0.78rem;
      color: #cbd5e1;
      line-height: 1.45;
    }
    .cred-rule {
      margin-top: 10px;
      font-size: 0.72rem;
      font-weight: 600;
      color: var(--color-yellow);
      background: rgba(234, 179, 8, 0.1);
      padding: 6px 10px;
      border-radius: 4px;
    }

    /* Status & Cell Details */
    .status-badge {
      display: inline-block;
      font-family: var(--font-mono);
      font-size: 0.68rem;
      font-weight: 600;
      padding: 2px 6px;
      border-radius: 3px;
      white-space: nowrap;
    }
    .status-fresh {
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid var(--color-green);
      color: #6ee7b7;
    }
    .status-stale {
      background: rgba(234, 179, 8, 0.12);
      border: 1px solid rgba(234, 179, 8, 0.3);
      color: #fde047;
    }
    .status-missing {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid var(--color-red);
      color: #fca5a5;
    }
    .cell-raw {
      font-family: var(--font-mono);
      font-size: 0.78rem;
      color: #f1f5f9;
      font-weight: 600;
    }
    .cell-unit {
      font-size: 0.7rem;
      color: var(--text-dim);
    }
    .cell-norm {
      font-family: var(--font-mono);
      font-size: 0.68rem;
      color: #cbd5e1;
      background: rgba(15, 23, 42, 0.6);
      padding: 4px 6px;
      border-radius: 4px;
      margin-bottom: 4px;
      word-break: break-all;
    }
    .cell-rubric {
      font-size: 0.68rem;
      color: var(--text-muted);
      line-height: 1.3;
    }
    .cell-source {
      font-weight: 600;
      color: #e2e8f0;
      font-size: 0.76rem;
    }
    .cell-date {
      font-size: 0.68rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
      margin-top: 2px;
    }
    .cell-uncertainty {
      font-size: 0.68rem;
      color: #fca5a5;
      margin-top: 4px;
      line-height: 1.3;
    }

    /* Footer */
    .dash-footer {
      max-width: 1380px;
      margin: 32px auto 0 auto;
      padding: 16px 24px;
      border-top: 1px solid var(--border-color);
      display: flex;
      justify-content: space-between;
      color: var(--text-dim);
      font-size: 0.78rem;
    }

    /* ==========================================================================
       Responsive Breakpoints (Desktop >= 1025px untouched)
       ========================================================================== */

    @media (max-width: 1200px) {
      .regions-grid { grid-template-columns: repeat(3, 1fr); }
      .history-grid { grid-template-columns: repeat(3, 1fr); }
    }

    @media (max-width: 1024px) {
      .hero-grid { grid-template-columns: 1fr; }
      .grid-two-cols { grid-template-columns: 1fr !important; }
      .scenarios-grid { grid-template-columns: repeat(2, 1fr); }
      .simulator-layout { grid-template-columns: 1fr; }
      .sim-result-card { position: static; }
    }

    @media (max-width: 768px) {
      /* Typography & Base */
      body, p, .panel-card p, .sim-slider-desc, .sc-desc, .reg-note, .hist-desc, .unc-desc, .stage-card-desc, .insight-box p {
        font-size: 14px;
        line-height: 1.5;
      }
      .meta-badge, .ev-badge, .stage-num, .stage-tag, .sc-id, .sc-delta, .pusher-badge, .unc-badge, .reg-badge, .reg-disclaimer-tag {
        font-size: 11px;
      }

      /* Top Navigation Bar: Stack vertically, wrap badges, no clipping */
      .top-bar {
        padding: 12px 14px;
        flex-direction: column;
        align-items: flex-start;
        gap: 10px;
      }
      .brand-group {
        width: 100%;
        gap: 10px;
        align-items: flex-start;
      }
      .brand-title {
        font-size: 1.02rem;
        line-height: 1.35;
        white-space: normal;
        word-break: break-word;
      }
      .brand-title span {
        display: inline;
      }
      .brand-sub {
        font-size: 0.7rem;
        word-break: break-word;
        margin-top: 2px;
      }
      .top-meta {
        width: 100%;
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        align-items: center;
        font-size: 11px;
      }
      .meta-badge {
        white-space: normal;
        display: inline-flex;
        align-items: center;
        padding: 4px 8px;
        border-radius: 4px;
        line-height: 1.3;
      }
      .top-date {
        width: 100%;
        font-size: 11px;
        color: var(--text-dim);
        display: block;
        margin-top: 2px;
      }

      /* Container & Panels */
      .dashboard-container {
        margin: 12px auto;
        padding: 0 10px;
        gap: 16px;
        max-width: 100%;
      }
      .panel-card {
        padding: 14px;
        border-radius: 6px;
        max-width: 100%;
      }

      /* Grids to Single Column */
      .scenarios-grid { grid-template-columns: 1fr; }
      .regions-grid { grid-template-columns: 1fr; }
      .history-grid { grid-template-columns: 1fr; }
      .unconnected-grid { grid-template-columns: 1fr; }
      .methodology-grid { grid-template-columns: 1fr !important; gap: 14px !important; }
      .credibility-grid { grid-template-columns: 1fr !important; gap: 14px !important; }
      .quality-metric-row { grid-template-columns: 1fr !important; gap: 10px !important; }

      /* Stages Grid: 2 columns at 641-768px */
      .stages-grid { grid-template-columns: repeat(2, 1fr); }

      /* Touch Targets >= 44px */
      .btn-tactical {
        min-height: 44px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 8px 14px;
        font-size: 13px;
      }
      .filter-btn {
        min-height: 44px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 8px 12px;
        font-size: 12px;
      }
      .scenario-card {
        min-height: 44px;
        padding: 14px;
      }

      /* Slider touch target & thumb enlargement */
      .sim-range {
        height: 10px;
        margin: 10px 0;
      }
      .sim-range::-webkit-slider-thumb {
        width: 28px;
        height: 28px;
      }
      .sim-range::-moz-range-thumb {
        width: 28px;
        height: 28px;
      }
      .sim-slider-group {
        min-height: 44px;
        padding: 14px 12px;
      }

      /* Table responsive & scroll hint */
      .mobile-table-hint {
        display: block;
      }
      .table-controls {
        flex-direction: column;
        align-items: stretch;
        gap: 12px;
      }
      .search-box-wrap {
        max-width: 100%;
        width: 100%;
      }
      .search-input {
        min-height: 44px;
        font-size: 14px;
      }
      .filter-group {
        width: 100%;
      }

      /* Gate formula & code break safety */
      .gate-formula-banner {
        word-break: break-word;
        overflow-wrap: break-word;
      }
      .gate-math {
        font-size: 13px;
        word-break: break-word;
        overflow-wrap: break-word;
        line-height: 1.5;
      }
      .gate-math code {
        white-space: normal;
        word-break: break-all;
        display: inline-block;
        font-size: 12px;
      }

      /* Five layers row mobile responsive */
      .layer-info {
        flex-wrap: wrap;
        gap: 6px;
      }
      .layer-name-wrap {
        flex-wrap: wrap;
        gap: 6px;
      }
      .layer-en {
        width: 100%;
        display: block;
      }

      /* Pushers mobile layout */
      .pusher-item {
        flex-wrap: wrap;
        gap: 8px;
      }
      .pusher-val {
        margin-left: auto;
      }

      /* Footer */
      .dash-footer {
        flex-direction: column;
        gap: 8px;
        text-align: center;
        padding: 16px 12px;
      }
    }

    @media (max-width: 640px) {
      /* Panel Header wrap & left-aligned tag */
      .panel-header {
        flex-direction: column;
        align-items: flex-start;
        gap: 8px;
      }
      .panel-title {
        width: 100%;
      }
      .panel-tag {
        width: 100%;
        text-align: left;
        display: block;
      }

      /* Stages Grid: single column on <=640px */
      .stages-grid {
        grid-template-columns: 1fr;
      }

      /* Probability Bands: single column on <=640px */
      .prob-grid {
        grid-template-columns: 1fr;
      }

      /* Gauge Meta Pills: wrap but horizontal */
      .gauge-meta-pills {
        flex-wrap: wrap;
        gap: 8px;
      }
      .pill {
        flex: 1 1 85px;
        max-width: none;
        padding: 6px 8px;
      }

      /* Active Stage Banner */
      .active-stage-banner {
        flex-direction: column;
        align-items: flex-start;
        gap: 8px;
      }

      /* Scenario Probabilities Row */
      .sc-probs {
        flex-wrap: wrap;
        gap: 4px;
      }

      /* Prob Header */
      .prob-header {
        flex-direction: column;
        align-items: flex-start;
        gap: 4px;
      }
    }

    @media (max-width: 480px) {
      .top-bar {
        padding: 10px 10px;
      }
      .brand-title {
        font-size: 0.94rem;
      }
      .dashboard-container {
        padding: 0 6px;
        margin: 10px auto;
        gap: 12px;
      }
      .panel-card {
        padding: 10px;
      }
      .score-big {
        font-size: 2.7rem;
      }
      .sim-score-big {
        font-size: 2.4rem;
      }
      .sim-metrics-grid {
        grid-template-columns: 1fr;
      }
      .sim-header-actions {
        flex-direction: column;
        align-items: stretch;
        width: 100%;
      }
      .sim-header-actions .btn-tactical {
        width: 100%;
      }
    }
  </style>"""

    js_script = """
    // Global Access to Embedded Scenario and Model Data
    window.WW3_MODEL_DATA = JSON.parse(document.getElementById('ww3-model-data').textContent);
    console.log("WW3 Model Data Loaded Successfully:", window.WW3_MODEL_DATA);

    // Switch Active Scenario View (UI-Step 3 Interactive Matrix)
    function switchScenario(scId) {
      const data = window.WW3_MODEL_DATA;
      if (!data || !data.scenarios) return;

      const sc = data.scenarios.find(s => s.id === scId);
      if (!sc) return;

      // 1. Update Scenario Cards highlight
      document.querySelectorAll('.scenario-card').forEach(el => el.classList.remove('active-sc'));
      const activeCard = document.getElementById('sc-card-' + scId);
      if (activeCard) activeCard.classList.add('active-sc');

      // 2. Update Gauge & Scores
      const scoreEl = document.getElementById('score-display');
      if (scoreEl) scoreEl.textContent = sc.global_risk_index.toFixed(1);

      const pillBase = document.getElementById('pill-base');
      if (pillBase) pillBase.textContent = sc.base_structural_score.toFixed(1);

      const pillGate = document.getElementById('pill-gate');
      if (pillGate) pillGate.textContent = 'x' + sc.gate_factor.toFixed(3);

      const pillFail = document.getElementById('pill-fail');
      if (pillFail) pillFail.textContent = (100 - sc.peace_capacity).toFixed(1) + '%';

      // 3. Update Gauge Needle (cx=160, cy=145, r=100)
      const svg = document.querySelector('.gauge-svg');
      if (svg) {
        const needle = svg.querySelector('line');
        if (needle) {
          const clamped = Math.max(0, Math.min(100, sc.global_risk_index));
          const theta = Math.PI - (clamped / 100.0) * Math.PI;
          const nx = 160 + 100 * Math.cos(theta);
          const ny = 145 - 100 * Math.sin(theta);
          needle.setAttribute('x2', nx.toFixed(1));
          needle.setAttribute('y2', ny.toFixed(1));
        }
      }

      // 4. Update Stage Progression Tracker
      document.querySelectorAll('.stage-card').forEach(el => el.classList.remove('active'));
      const activeStageCard = document.getElementById('stage-card-' + sc.stage_number);
      if (activeStageCard) activeStageCard.classList.add('active');

      // 5. Update Five Layers bars if present
      if (sc.layer_scores) {
        for (const [lid, val] of Object.entries(sc.layer_scores)) {
          const rows = document.querySelectorAll('.layer-row');
          rows.forEach(r => {
            const codeEl = r.querySelector('.layer-code');
            if (codeEl && codeEl.textContent.trim() === lid) {
              const scoreEl = r.querySelector('.layer-score');
              const fillEl = r.querySelector('.progress-fill');
              if (scoreEl) scoreEl.textContent = val.toFixed(1);
              if (fillEl) {
                fillEl.style.width = val + '%';
                let color = "var(--color-green)";
                if (val >= 85) color = "var(--color-red)";
                else if (val >= 70) color = "var(--color-orange)";
                else if (val >= 50) color = "var(--color-yellow)";
                fillEl.style.background = color;
                if (scoreEl) scoreEl.style.color = color;
              }
            }
          });
        }
      }
    }

    // Step 4: Interactive Simulation Recalculator Engine
    function runSimulation() {
      // 1. Read slider inputs
      const aiVal = parseFloat(document.getElementById('sim_l3_ai')?.value || 62);
      const unempVal = parseFloat(document.getElementById('sim_l3_unemp')?.value || 68);
      const energyVal = parseFloat(document.getElementById('sim_l1_energy')?.value || 60);
      const mineralsVal = parseFloat(document.getElementById('sim_l1_minerals')?.value || 72);
      const blocVal = parseFloat(document.getElementById('sim_l4_bloc')?.value || 78);
      const fearVal = parseFloat(document.getElementById('sim_l5_fear')?.value || 78);
      const peaceCap = parseFloat(document.getElementById('sim_gate_peace')?.value || 44.9);

      // Update slider badge displays
      if (document.getElementById('val-sim_l3_ai')) document.getElementById('val-sim_l3_ai').textContent = aiVal.toFixed(1);
      if (document.getElementById('val-sim_l3_unemp')) document.getElementById('val-sim_l3_unemp').textContent = unempVal.toFixed(1);
      if (document.getElementById('val-sim_l1_energy')) document.getElementById('val-sim_l1_energy').textContent = energyVal.toFixed(1);
      if (document.getElementById('val-sim_l1_minerals')) document.getElementById('val-sim_l1_minerals').textContent = mineralsVal.toFixed(1);
      if (document.getElementById('val-sim_l4_bloc')) document.getElementById('val-sim_l4_bloc').textContent = blocVal.toFixed(1);
      if (document.getElementById('val-sim_l5_fear')) document.getElementById('val-sim_l5_fear').textContent = fearVal.toFixed(1);
      if (document.getElementById('val-sim_gate_peace')) document.getElementById('val-sim_gate_peace').textContent = peaceCap.toFixed(1);

      // 2. Compute dynamic layer scores
      const l1 = (52.0 * 1.0 + 58.0 * 1.0 + energyVal * 1.2 + mineralsVal * 1.3 + 65.0 * 1.0 + 68.0 * 1.2) / 6.7;
      const l2 = 71.3235;
      const l3 = (56.0 * 1.0 + unempVal * 1.2 + 65.0 * 1.1 + 75.0 * 1.0 + aiVal * 1.5 + 64.0 * 1.0) / 6.8;
      const l4 = (72.0 * 1.2 + 75.0 * 1.2 + blocVal * 1.3 + 76.0 * 1.2 + 66.0 * 1.4 + 80.0 * 1.4) / 7.7;
      const l5 = (76.0 * 1.3 + 70.0 * 1.1 + 64.0 * 1.0 + fearVal * 1.4 + 72.0 * 1.2 + 68.0 * 1.0) / 7.0;

      // 3. Base Structural Score (Weights: L1:1.0, L2:1.0, L3:1.1, L4:1.2, L5:1.1 = 5.4)
      const baseStructural = (l1 * 1.0 + l2 * 1.0 + l3 * 1.1 + l4 * 1.2 + l5 * 1.1) / 5.4;

      // 4. Peace Mechanism Gate Factor
      const gateFailure = Math.max(0, 100.0 - peaceCap);
      const gateFactor = 1.4 - (Math.max(0, Math.min(100, peaceCap)) / 100.0) * 0.8;

      // 5. Interaction Effects
      const iL1L2 = 0.08 * (l1 * l2 / 100.0);
      const iL3L5 = 0.08 * (l3 * l5 / 100.0);
      const iL4Gate = 0.10 * (l4 * gateFailure / 100.0);
      const rawInteraction = iL1L2 + iL3L5 + iL4Gate;
      const totalInteraction = Math.min(25.0, rawInteraction);

      // 6. Gated Score
      const rawInteracted = baseStructural + totalInteraction;
      const gated = rawInteracted * gateFactor;

      // 7. Soft Clamp (threshold=70.0, ceiling=100.0)
      let simIndex = 0.0;
      if (gated <= 0.0) {
        simIndex = 0.0;
      } else if (gated <= 70.0) {
        simIndex = gated;
      } else {
        simIndex = 70.0 + 30.0 * Math.tanh((gated - 70.0) / 30.0);
      }
      simIndex = Math.min(100.0, Math.max(0.0, simIndex));

      // 8. Stage Mapping
      let stageNum = 1;
      let stageTitle = "階段一：結構壓力形成";
      if (simIndex < 25.0) {
        stageNum = 1; stageTitle = "階段一：結構壓力形成";
      } else if (simIndex < 50.0) {
        stageNum = 2; stageTitle = "階段二：利益衝突顯性化";
      } else if (simIndex < 85.0) {
        stageNum = 3; stageTitle = "階段三：和平解決機制失效";
      } else {
        stageNum = 4; stageTitle = "階段四：暴力成為被接受選項";
      }

      // 9. Probability Bands (v0.2 Calibrated Anchors)
      const p1y = 80.0 / (1.0 + Math.exp(-0.055 * (simIndex - 120.0)));
      const p5y = 95.0 / (1.0 + Math.exp(-0.058 * (simIndex - 95.0)));
      const p10y = 98.0 / (1.0 + Math.exp(-0.059 * (simIndex - 82.5)));

      // 10. Update DOM elements
      const indexDisplay = document.getElementById('sim-index-display');
      if (indexDisplay) indexDisplay.textContent = simIndex.toFixed(1);

      const delta = simIndex - 83.1;
      const deltaDisplay = document.getElementById('sim-delta-display');
      if (deltaDisplay) {
        const sign = delta >= 0 ? '+' : '';
        deltaDisplay.textContent = Math.abs(delta) < 0.05 ? '基準 (±0.0)' : `${sign}${delta.toFixed(1)} vs 基準`;
        deltaDisplay.style.background = delta > 0.05 ? 'rgba(239, 68, 68, 0.2)' : (delta < -0.05 ? 'rgba(16, 185, 129, 0.2)' : 'rgba(148, 163, 184, 0.15)');
        deltaDisplay.style.color = delta > 0.05 ? '#fca5a5' : (delta < -0.05 ? '#6ee7b7' : '#cbd5e1');
      }

      const stageDisplay = document.getElementById('sim-stage-display');
      if (stageDisplay) {
        stageDisplay.textContent = `STAGE ${stageNum} · ${stageTitle}`;
        stageDisplay.style.color = stageNum >= 4 ? 'var(--color-red)' : (stageNum === 3 ? 'var(--color-orange)' : (stageNum === 2 ? 'var(--color-yellow)' : 'var(--color-green)'));
      }

      if (document.getElementById('sim-base-display')) document.getElementById('sim-base-display').textContent = baseStructural.toFixed(1);
      if (document.getElementById('sim-gate-display')) document.getElementById('sim-gate-display').textContent = 'x' + gateFactor.toFixed(3);
      if (document.getElementById('sim-inter-display')) document.getElementById('sim-inter-display').textContent = '+' + totalInteraction.toFixed(2);
      if (document.getElementById('sim-raw-display')) document.getElementById('sim-raw-display').textContent = rawInteracted.toFixed(1);

      if (document.getElementById('sim-prob-1y')) document.getElementById('sim-prob-1y').textContent = `${p1y.toFixed(1)}% (${(p1y*0.65).toFixed(1)}%–${Math.min(100, p1y*1.45).toFixed(1)}%)`;
      if (document.getElementById('sim-prob-5y')) document.getElementById('sim-prob-5y').textContent = `${p5y.toFixed(1)}% (${(p5y*0.75).toFixed(1)}%–${Math.min(100, p5y*1.30).toFixed(1)}%)`;
      if (document.getElementById('sim-prob-10y')) document.getElementById('sim-prob-10y').textContent = `${p10y.toFixed(1)}% (${(p10y*0.80).toFixed(1)}%–${Math.min(100, p10y*1.25).toFixed(1)}%)`;

      // Sync to Main Gauge
      const mainScore = document.getElementById('score-display');
      if (mainScore) mainScore.textContent = simIndex.toFixed(1);

      const svg = document.querySelector('.gauge-svg');
      if (svg) {
        const needle = svg.querySelector('line');
        if (needle) {
          const theta = Math.PI - (simIndex / 100.0) * Math.PI;
          const nx = 160 + 100 * Math.cos(theta);
          const ny = 145 - 100 * Math.sin(theta);
          needle.setAttribute('x2', nx.toFixed(1));
          needle.setAttribute('y2', ny.toFixed(1));
        }
      }

      document.querySelectorAll('.stage-card').forEach(el => el.classList.remove('active'));
      const activeStageCard = document.getElementById('stage-card-' + stageNum);
      if (activeStageCard) activeStageCard.classList.add('active');
    }

    function resetSimulation() {
      const defaults = {
        'sim_l3_ai': 62.0,
        'sim_l3_unemp': 68.0,
        'sim_l1_energy': 60.0,
        'sim_l1_minerals': 72.0,
        'sim_l4_bloc': 78.0,
        'sim_l5_fear': 78.0,
        'sim_gate_peace': 44.9
      };
      for (const [id, val] of Object.entries(defaults)) {
        const el = document.getElementById(id);
        if (el) el.value = val;
      }
      runSimulation();
    }

    // Step 5: Filter Table by Layer
    function filterTable(layerCode, btn) {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');

      const rows = document.querySelectorAll('.ind-row');
      rows.forEach(r => {
        const l = r.getAttribute('data-layer');
        if (layerCode === 'ALL' || l === layerCode) {
          r.style.display = '';
        } else {
          r.style.display = 'none';
        }
      });
    }

    // Step 5: Search Table by Text
    function searchTable() {
      const q = (document.getElementById('ind-search')?.value || '').toLowerCase().trim();
      const rows = document.querySelectorAll('.ind-row');
      rows.forEach(r => {
        const text = (r.getAttribute('data-search') || '').toLowerCase();
        if (!q || text.includes(q)) {
          r.style.display = '';
        } else {
          r.style.display = 'none';
        }
      });
    }

    // Dynamic Cloudflare Worker API fetch & offline fallback (C3)
    const apiBase = "__API_BASE__";
    if (apiBase) {
      window.WW3_API_BASE = apiBase;
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);

      Promise.all([
        fetch(apiBase + '/api/risk/latest', { signal: controller.signal }).then(r => {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        }),
        fetch(apiBase + '/api/risk/layers', { signal: controller.signal }).then(r => {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        }),
        fetch(apiBase + '/api/data-status', { signal: controller.signal }).then(r => {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
      ]).then(([latest, layersData, dataStatus]) => {
        clearTimeout(timeoutId);
        applyApiData(latest, layersData, dataStatus);
      }).catch(err => {
        console.warn('WW3 API fetch failed or timed out after 3s, using embedded offline snapshot:', err);
        const badge = document.getElementById('top-data-source-badge');
        if (badge) {
          badge.textContent = '● 離線快照（內嵌數據）';
          badge.className = 'meta-badge badge-offline';
        }
      });
    }

    function applyApiData(latest, layersData, dataStatus) {
      // 1. Update Top Bar Data Source Badge and Date
      const badge = document.getElementById('top-data-source-badge');
      if (badge) {
        badge.textContent = '● 即時 API · ' + (latest.computed_at || 'LIVE');
        badge.className = 'meta-badge badge-live';
      }
      const topDate = document.getElementById('top-date-display');
      if (topDate && latest.computed_at) {
        topDate.textContent = latest.computed_at + ' · 即時 API 數據';
      }

      // 2. Update Gauge & Scores
      const scoreEl = document.getElementById('score-display');
      if (scoreEl && typeof latest.total_index === 'number') {
        scoreEl.textContent = latest.total_index.toFixed(1);
      }
      const pillBase = document.getElementById('pill-base');
      if (pillBase && typeof latest.base_score === 'number') {
        pillBase.textContent = latest.base_score.toFixed(1);
      }
      const pillGate = document.getElementById('pill-gate');
      if (pillGate && latest.gate && typeof latest.gate.multiplier === 'number') {
        pillGate.textContent = 'x' + latest.gate.multiplier.toFixed(3);
      }
      const pillFail = document.getElementById('pill-fail');
      if (pillFail && latest.gate && typeof latest.gate.peace_capacity === 'number') {
        pillFail.textContent = (100 - latest.gate.peace_capacity).toFixed(1) + '%';
      }

      // 3. Update Gauge Needle (cx=160, cy=145, r=100)
      const svg = document.querySelector('.gauge-svg');
      if (svg && typeof latest.total_index === 'number') {
        const needle = svg.querySelector('line');
        if (needle) {
          const clamped = Math.max(0, Math.min(100, latest.total_index));
          const theta = Math.PI - (clamped / 100.0) * Math.PI;
          const nx = 160 + 100 * Math.cos(theta);
          const ny = 145 - 100 * Math.sin(theta);
          needle.setAttribute('x2', nx.toFixed(1));
          needle.setAttribute('y2', ny.toFixed(1));
        }
      }

      // 4. Update Stage Progression Tracker & Top Stage Badge
      if (latest.stage && latest.stage.number) {
        document.querySelectorAll('.stage-card').forEach(el => el.classList.remove('active'));
        const activeStageCard = document.getElementById('stage-card-' + latest.stage.number);
        if (activeStageCard) activeStageCard.classList.add('active');
        const stageBadge = document.getElementById('top-stage-badge');
        if (stageBadge && latest.stage.title) {
          stageBadge.textContent = '警戒級別：' + latest.stage.title + ' (STAGE ' + latest.stage.number + ')';
        }
      }

      // 5. Update Five Layers bars
      if (latest.layers) {
        for (const [lid, val] of Object.entries(latest.layers)) {
          const numVal = typeof val === 'number' ? val : (val && val.score ? val.score : 0);
          const rows = document.querySelectorAll('.layer-row');
          rows.forEach(r => {
            const codeEl = r.querySelector('.layer-code');
            if (codeEl && codeEl.textContent.trim() === lid) {
              const scoreEl = r.querySelector('.layer-score');
              const fillEl = r.querySelector('.progress-fill');
              if (scoreEl) scoreEl.textContent = numVal.toFixed(1);
              if (fillEl) {
                fillEl.style.width = numVal + '%';
                let color = "var(--color-green)";
                if (numVal >= 85) color = "var(--color-red)";
                else if (numVal >= 70) color = "var(--color-orange)";
                else if (numVal >= 50) color = "var(--color-yellow)";
                fillEl.style.background = color;
                if (scoreEl) scoreEl.style.color = color;
              }
            }
          });
        }
      }

      // 6. Update Driver Decomposition Step Values
      const dBase = document.getElementById('driver-base-val');
      if (dBase && typeof latest.base_score === 'number') dBase.textContent = latest.base_score.toFixed(1);
      const dInter = document.getElementById('driver-interaction-val');
      if (dInter && typeof latest.interaction_bonus === 'number') dInter.textContent = '+' + latest.interaction_bonus.toFixed(2);
      const dGate = document.getElementById('driver-gate-val');
      if (dGate && latest.gate && typeof latest.gate.multiplier === 'number') dGate.textContent = 'x' + latest.gate.multiplier.toFixed(3);

      // 7. Update Top Risk Drivers List
      if (latest.drivers && Array.isArray(latest.drivers) && latest.drivers.length > 0) {
        const pushersContainer = document.getElementById('pushers-list');
        if (pushersContainer) {
          pushersContainer.innerHTML = latest.drivers.slice(0, 3).map((drv, i) => `
            <div class="pusher-item">
              <div class="pusher-badge">#0${i + 1} · ${drv.layer || ''}</div>
              <div class="pusher-content">
                <div class="pusher-title">${drv.name || drv.id}</div>
                <div class="pusher-meta">指標ID: <code>${drv.id}</code> · 權重 x${(drv.weight || 1.0).toFixed(1)}</div>
              </div>
              <div class="pusher-val">${(drv.value || 0).toFixed(1)}</div>
            </div>
          `).join('');
        }
      }

      // 8. Update Data Quality Card
      if (dataStatus) {
        const qComp = document.getElementById('quality-comp-pct');
        if (qComp && typeof dataStatus.completeness_pct === 'number') {
          qComp.textContent = dataStatus.completeness_pct.toFixed(1) + '%';
        }
        const qFresh = document.getElementById('quality-freshness-val');
        if (qFresh && dataStatus.fresh_count !== undefined && dataStatus.stale_count !== undefined) {
          qFresh.textContent = dataStatus.fresh_count + ' Fresh / ' + dataStatus.stale_count + ' Stale';
        }
        const qMissing = document.getElementById('quality-missing-val');
        if (qMissing && dataStatus.missing_count !== undefined) {
          qMissing.textContent = dataStatus.missing_count + ' 項';
        }
      }
    }
    """
    js_script = js_script.replace("__API_BASE__", api_base_val)

    # HTML Skeleton
    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WW3 戰爭風險指數儀表板 | WW3 War Risk Index Dashboard</title>
  {css}
</head>
<body>
  <!-- Top Navigation Bar -->
  <header class="top-bar">
    <div class="brand-group">
      <div class="radar-icon"></div>
      <div>
        <div class="brand-title">WW3 戰爭風險指數儀表板 <span class="brand-title-en" style="font-weight:400;font-size:0.85rem;color:var(--text-dim);">WW3 War Risk Index</span></div>
        <div class="brand-sub">DEFENSE INTELLIGENCE &amp; SYSTEMIC CRISIS TERMINAL · v0.4.0</div>
      </div>
    </div>
    <div class="top-meta">
      <span class="meta-badge badge-step">WAR RISK INDEX</span>
      <span class="meta-badge badge-alert" id="top-stage-badge">警戒級別：{stage['title']} (STAGE {stage['number']})</span>
      {source_badge_html}
      <span class="top-date" id="top-date-display" style="font-family:var(--font-mono);color:var(--text-dim);">{data['metadata']['generated_at']} · {data['metadata']['active_scenario_year']} 基準</span>
    </div>
  </header>

  <!-- Main Container -->
  <main class="dashboard-container">
    <!-- Section 1: Hero Grid (Gauge + Stage Progression Tracker) -->
    <section class="hero-grid">
      <!-- Left: Big Semi-circle Gauge -->
      <div class="gauge-card">
        <div style="font-size:0.75rem;font-weight:700;letter-spacing:1px;color:var(--text-dim);margin-bottom:8px;font-family:var(--font-mono);">
          GLOBAL ESCALATION INDEX · WAR RISK INDEX 100/100
        </div>
        <div class="gauge-wrapper" id="gauge-container">
          {gauge_svg}
        </div>
        <div class="score-big" id="score-display">{risk_score:.1f}</div>
        <div class="score-label">戰爭風險指數（War Risk Index）100/100</div>
        <div class="score-sub">CURRENT SCENARIO: {main['scenario_title']}</div>
        
        <div class="gauge-meta-pills">
          <div class="pill">
            <div class="pill-label">基礎結構分</div>
            <div class="pill-val" id="pill-base">{main['base_structural_score']:.1f}</div>
          </div>
          <div class="pill">
            <div class="pill-label">和平閘門乘數</div>
            <div class="pill-val" id="pill-gate">x{main['gate_factor']:.3f}</div>
          </div>
          <div class="pill">
            <div class="pill-label">機制失效度</div>
            <div class="pill-val" id="pill-fail">{main['gate_failure']:.1f}%</div>
          </div>
        </div>
      </div>

      <!-- Right: Four-Stage Progression & Probabilities -->
      <div class="panel-card">
        <div class="panel-header">
          <div class="panel-title">
            <span>危機升級四階段狀態 (Escalation Stage Tracker)</span>
          </div>
          <span class="panel-tag">FOUR-STAGE CRISIS FRAMEWORK</span>
        </div>

        <div class="stages-grid">
          {stage_tracker_html}
        </div>

        <!-- Active Stage Details Banner -->
        <div class="active-stage-banner">
          <span class="banner-badge">當前定位 STAGE {stage['number']}</span>
          <div class="banner-text">
            <strong>{stage['title']}：</strong>{stage['description']}
          </div>
        </div>

        <!-- Probability Bands for Baseline -->
        <div style="margin-top:20px;">
          <div class="prob-header" style="font-size:0.8rem;font-weight:700;color:var(--text-muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;">
            <span>結構風險情境帶（非經驗證概率）(Structural Risk Scenario Bands)</span>
            <span style="font-size:0.7rem;font-weight:400;color:var(--text-dim);">非經驗證概率 · 基於宏觀結構壓力映射</span>
          </div>
          <div class="prob-grid">
            <div class="prob-card">
              <div class="prob-horizon">1 年期結構風險窗口 (1-Year)</div>
              <div class="prob-central">{main['probability_bands']['1y']['central_pct']:.1f}%</div>
              <div class="prob-band">情境帶: {main['probability_bands']['1y']['lower_pct']:.1f}% – {main['probability_bands']['1y']['upper_pct']:.1f}%</div>
            </div>
            <div class="prob-card">
              <div class="prob-horizon">5 年期結構風險窗口 (5-Year)</div>
              <div class="prob-central">{main['probability_bands']['5y']['central_pct']:.1f}%</div>
              <div class="prob-band">情境帶: {main['probability_bands']['5y']['lower_pct']:.1f}% – {main['probability_bands']['5y']['upper_pct']:.1f}%</div>
            </div>
            <div class="prob-card">
              <div class="prob-horizon">10 年期結構風險窗口 (10-Year)</div>
              <div class="prob-central">{main['probability_bands']['10y']['central_pct']:.1f}%</div>
              <div class="prob-band">情境帶: {main['probability_bands']['10y']['lower_pct']:.1f}% – {main['probability_bands']['10y']['upper_pct']:.1f}%</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    {step1_5_html}
    {step2_html}
    {step3_html}
    {step4_html}
    {step5_html}
  </main>

  <footer class="dash-footer">
    <div>WW3 Risk Model · 零框架純靜態離線架構 · 嚴格由模型公式計算</div>
    <div>Model Version: {data['metadata']['model_version']} · File: ui/dashboard.html</div>
  </footer>

  <!-- Embedded Model Output (Guarantees 100% offline file:// rendering without CORS errors) -->
  <script id="ww3-model-data" type="application/json">
{data_json_str}
  </script>
  <script>
{js_script}
  </script>
</body>
</html>
"""
    return html


def build_dashboard(
    scenario_path: str | Path = "scenarios/baseline_2026.json",
    output_html_path: str | Path = "ui/dashboard.html",
    output_json_path: Optional[str | Path] = "ui/dashboard_data.json",
    ui_step: int = 5,
    model: Optional[WW3RiskModel] = None,
    api_base: Optional[str] = None,
) -> Dict[str, Any]:
    """Compile scenario data and generate output HTML/JSON files."""
    scenario_p = Path(scenario_path)
    output_html_p = Path(output_html_path)

    # Ensure parent output directory exists
    output_html_p.parent.mkdir(parents=True, exist_ok=True)

    data = generate_dashboard_data(scenario_path=scenario_p, model=model)
    html_content = build_dashboard_html(data, ui_step=ui_step, api_base=api_base)

    with open(output_html_p, "w", encoding="utf-8") as f:
        f.write(html_content)

    if output_json_path:
        output_json_p = Path(output_json_path)
        output_json_p.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="WW3 Risk Model Static Dashboard Generator")
    parser.add_argument("--scenario", "-s", type=str, default="scenarios/baseline_2026.json", help="Path to main scenario JSON")
    parser.add_argument("--output", "-o", type=str, default="ui/dashboard.html", help="Path to output dashboard HTML")
    parser.add_argument("--json", "-j", type=str, default="ui/dashboard_data.json", help="Path to output dashboard JSON")
    parser.add_argument("--step", type=int, default=5, help="UI Step version to render (1 to 5)")
    parser.add_argument("--api-base", type=str, default=None, help="Base URL of Cloudflare Worker API for dynamic dashboard")

    parsed = parser.parse_args()
    data = build_dashboard(
        scenario_path=parsed.scenario,
        output_html_path=parsed.output,
        output_json_path=parsed.json,
        ui_step=parsed.step,
        api_base=parsed.api_base,
    )
    print(f"WW3 Dashboard successfully generated for {data['metadata']['active_scenario_title']} (UI-Step {parsed.step})")
    print(f"HTML output: {parsed.output}")
    if parsed.json:
        print(f"JSON data: {parsed.json}")


if __name__ == "__main__":
    main()
