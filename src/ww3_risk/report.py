"""Markdown report generator for WW3 Risk Model evaluations."""

from __future__ import annotations

from typing import List, Optional
from . import __version__
from .model import RiskResult
from .indicators import ScenarioData


def generate_markdown_report(result: RiskResult, scenario: Optional[ScenarioData] = None) -> str:
    """Generate a comprehensive Markdown analysis report adhering to v0.3 standards."""
    lines: List[str] = []

    lines.append(f"# WW3 結構風險評估報告：{result.scenario_title}")
    lines.append("")
    lines.append(f"> **情境識別碼**：`{result.scenario_id}` | **年份**：{result.scenario_year} | **模型版本**：v{__version__}")
    lines.append("")

    # 1. 核心評估摘要
    lines.append("## 一、核心評估指標與階段定位")
    lines.append("")
    lines.append("| 指標項目 | 數值 / 狀態 | 解讀說明 |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(f"| **戰爭風險指數 (War Risk Index)** | **{result.global_risk_index:.1f} / 100** | 綜合五層結構壓力、互動效應與和平閘門後之總體風險（非經驗證開戰概率） |")
    lines.append(f"| **當前危機階段 (Stage)** | **{result.stage.title}** (`{result.stage.code}`) | {result.stage.description} |")
    lines.append(f"| **基礎五層結構分 (Base Score)** | {result.base_structural_score:.1f} / 100 | 五層指標加權平均（未計互動與閘門） |")
    lines.append(f"| **互動放大加成 (Interaction Bonus)** | +{result.interactions['total']:.2f} (上限 {result.interactions.get('is_capped', False) and '已達上限' or '未達上限'}) | 複合危機之超線性耦合效應 |")
    lines.append(f"| **和平機制閘門係數 (Gate Multiplier)** | **x{result.gate_factor:.3f}** | 和平能力 {result.peace_capacity:.1f} / 100 (失效度 {result.gate_failure:.1f}%) |")
    lines.append("")

    # 2. 五層結構分數明細
    lines.append("## 二、五層結構風險明細 (Five Structural Layers)")
    lines.append("")
    lines.append("| 層級編號 | 維度名稱 | 維度名稱 (EN) | 得分 (0-100) | 權重 | 風險狀態評估 |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

    layer_meta = {
        "L1": ("生存／資源稀缺", "Survival / Resource Scarcity"),
        "L2": ("分配失衡", "Inequality & Distribution"),
        "L3": ("工作／生計／AI取代", "Labor, Livelihood & AI"),
        "L4": ("權力／安全困境", "Power & Security Dilemma"),
        "L5": ("對未來的恐懼／預防邏輯", "Fear of Future & Preventive Logic"),
    }

    for lid in ["L1", "L2", "L3", "L4", "L5"]:
        score = result.layer_scores.get(lid, 0.0)
        weight = result.layer_weights.get(lid, 1.0)
        c_name, e_name = layer_meta.get(lid, (lid, lid))
        status = "低度 (Low)" if score < 35 else ("中度 (Moderate)" if score < 60 else ("高度警戒 (High)" if score < 80 else "極度危險 (Critical)"))
        lines.append(f"| **{lid}** | {c_name} | {e_name} | **{score:.1f}** | {weight:.1f} | {status} |")

    lines.append("")

    # 3. 和平機制閘門分析
    lines.append("## 三、和平機制閘門分析 (Peace Mechanism Gate)")
    lines.append("")
    lines.append("和平機制並非單純平均加權的一層，而是調節所有結構壓力能否轉化為戰爭爆發的**閘門緩衝器**：")
    lines.append(f"- **和平機制容量 (Peace Capacity)**：`{result.peace_capacity:.1f} / 100`")
    lines.append(f"- **機制失效度 (Gate Failure)**：`{result.gate_failure:.1f} / 100`")
    lines.append(f"- **閘門乘數 (Gate Factor)**：`x{result.gate_factor:.3f}`（介於 0.60 至 1.40；>1.0 代表機制失效助長風險，<1.0 代表制度有效壓制風險）")
    lines.append("")
    lines.append("### 當前和平緩衝器狀態")
    lines.append("| 緩衝機制名稱 | 有效容量 (0-100) | 權重 | 說明 |")
    lines.append("| :--- | :--- | :--- | :--- |")
    for buf in result.top_peace_buffers:
        lines.append(f"| {buf['name']} (`{buf['id']}`) | {buf['capacity']:.1f} | {buf['weight']:.1f} | 數值越高代表避戰緩衝越穩固 |")
    lines.append("")

    # 4. 互動效應分析
    lines.append("## 四、系統互動加成效應 (Interaction Effects)")
    lines.append("")
    lines.append("戰爭很少源自單一維度問題，模型檢驗了以下核心交叉共振：")
    lines.append("")
    lines.append("| 互動維度 | 核心動力學機制 | 加成得分 | 狀態 |")
    lines.append("| :--- | :--- | :--- | :--- |")
    lines.append(f"| **L1 × L2** | 資源短缺遇上分配不均，階級摩擦激化為總量爭奪 | +{result.interactions['L1_x_L2']:.2f} | 顯著共振 |")
    lines.append(f"| **L3 × L5** | 失業/AI取代遇上未來悲觀，社會絕望轉化為對外仇恨 | +{result.interactions['L3_x_L5']:.2f} | 顯著共振 |")
    lines.append(f"| **L4 × 閘門失效** | 安全困境遇上和平機制失效，雙方逼近預防性開戰門檻 | +{result.interactions['L4_x_GateFailure']:.2f} | 顯著共振 |")
    lines.append(f"| **合計互動加成** | 綜合共振項（上限受防護保護） | **+{result.interactions['total']:.2f}** | {'已觸及上限' if result.interactions.get('is_capped') else '正常累積'} |")
    lines.append("")

    # 5. 結構風險情境帶
    lines.append("## 五、結構風險情境帶（非經驗證概率） (Scenario Structural Risk Bands)")
    lines.append("")
    lines.append("> ⚠️ **重要說明**：本情境帶為基於結構壓力所推導之**結構風險情境帶（非經驗證概率）**，用於評估大國體系易燃度，**並非已驗證之高精度統計預測或開戰概率**。大國全面戰爭歷史基率極低，實際衝突爆發仍受隨機突發事件（Black Swan）、決策者個人意志及突發微觀危機所左右。")
    lines.append("")
    lines.append("| 時間跨度 (Horizon) | 結構情境帶 (Band) | 中位估值 (Central) | 跨度特徵與動力學說明 |")
    lines.append("| :--- | :--- | :--- | :--- |")
    for hid in ["1y", "5y", "10y"]:
        b = result.probability_bands[hid]
        desc = {
            "1y": "短期需要極端引信事件（Trigger Event）催化，通常受限於備戰週期與政治決心。",
            "5y": "中期結構性摩擦持續累積，經貿去風險與軍備交替升級，危機窗口頻繁開啟。",
            "10y": "長期面臨權力轉移（Thucydides Trap）、AI顛覆與人口老齡關閉窗口之預防性戰略決戰期。",
        }.get(hid, "")
        lines.append(f"| **{b.horizon_years} 年期** | `{b.lower_pct:.1f}% – {b.upper_pct:.1f}%` | **{b.central_pct:.1f}%** | {desc} |")
    lines.append("")

    # 6. 主要推動因素與減震因素
    lines.append("## 六、主要風險推手與和平減震機制")
    lines.append("")
    lines.append("### 前五大推高風險之關鍵指標 (Top Risk Pushers)")
    for i, drv in enumerate(result.top_risk_drivers, 1):
        lines.append(f"{i}. **[{drv['layer']}] {drv['name']}** (`{drv['id']}`): 數值 `{drv['value']:.1f}/100` (權重: {drv['weight']})")
    lines.append("")
    lines.append("### 有效減震緩衝 (Key Dampeners)")
    for buf in result.top_peace_buffers:
        if buf['capacity'] >= 50.0:
            lines.append(f"- **{buf['name']}** (`{buf['id']}`): 緩衝容量 `{buf['capacity']:.1f}/100`（尚具穩定作用）")
    lines.append("")

    # 7. 證據質量與數據品質
    lines.append("## 七、證據質量評級與數據品質監測 (Data Quality & Evidence)")
    lines.append("")
    lines.append(f"- **已驗證統計數據 (Verified)**: {result.evidence_counts.get('verified', 0)} 項 (官方權威公開統計)")
    lines.append(f"- **客觀代理推論數據 (Inference)**: {result.evidence_counts.get('inference', 0)} 項 (透明量化折算)")
    lines.append(f"- **結構推演示範數據 (Illustrative)**: {result.evidence_counts.get('illustrative', 0)} 項 (公開評分量表)")
    lines.append("")

    if scenario is not None:
        q = scenario.calculate_data_quality()
        lines.append(f"- **數據整體完整度**: `{q['completeness_pct']:.1f}%`")
        lines.append(f"- **新鮮度監測**: Fresh: {q['fresh_count']} 項 | Stale: {q['stale_count']} 項 | Missing: {q['missing_count']} 項")
        lines.append("- **即時性聲明**: 無即時自動 API 串接之指標均如實顯示最後觀測與發布年份，嚴禁聲稱即時監控。")
        lines.append("")

    lines.append("### 免責聲明 (Disclaimer)")
    lines.append("本模型僅供學術研究、系統動力學探討及戰略推演使用。本報告內容不構成任何國防、外交、政策或投資建議。模型不包含任何武器製造、戰術攻擊或鼓吹戰爭之內容，旨在識別系統性風險積累節點，促進和平機制的維護與改良。")
    lines.append("")

    return "\n".join(lines)
