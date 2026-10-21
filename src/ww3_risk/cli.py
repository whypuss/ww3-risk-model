"""Command line interface for the WW3 Risk Model."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import List

from .dashboard import build_dashboard
from .indicators import ScenarioData, load_scenario_from_file
from .model import WW3RiskModel
from .report import generate_markdown_report
from .scenarios import compare_scenarios, format_comparison_ascii_table
from .snapshot import export_snapshot_to_file


def format_data_quality_report(quality_dict: dict) -> str:
    """Format data quality dictionary into a readable CLI summary and table."""
    lines: List[str] = []
    sep = "=" * 80
    sub_sep = "-" * 80

    lines.append(sep)
    lines.append("WW3 風險模型 - 數據品質與更新新鮮度報告 (Data Quality Report)")
    lines.append(sep)
    lines.append(f"  評估基準日期 (As-of Date)    : {quality_dict.get('as_of_date', '2026-10-21')}")
    lines.append(f"  指標總數 (Total Indicators)   : {quality_dict.get('total_indicators', 0)} 項")
    lines.append(f"  整體數據完整度 (Completeness) : {quality_dict.get('completeness_pct', 0.0):.1f}%")
    lines.append(
        f"  狀態分佈 (Status Breakdown)   : "
        f"Fresh: {quality_dict.get('fresh_count', 0)} | "
        f"Stale: {quality_dict.get('stale_count', 0)} | "
        f"Missing: {quality_dict.get('missing_count', 0)}"
    )
    lines.append(sub_sep)
    lines.append(f"{'狀態':<8} {'層級':<6} {'指標代碼':<32} {'數值':<6} {'發布日期':<12} {'過期判定':<8} 來源")
    lines.append(sub_sep)

    status_tag = {
        "fresh": "[FRESH]",
        "stale": "[STALE]",
        "missing": "[MISSING]",
    }

    for it in quality_dict.get("items", []):
        tag = status_tag.get(it["status"], f"[{it['status'].upper()}]")
        lid = it.get("layer", "")
        iid = it.get("id", "")
        raw_val = str(it.get("raw_value") if it.get("raw_value") is not None else "-")[:6]
        pub_date = str(it.get("publication_date", "-"))[:12]
        stale_after = str(it.get("stale_after", "-"))[:8]
        src = str(it.get("source_name", "-"))[:35]
        lines.append(f"{tag:<8} {lid:<6} {iid:<32} {raw_val:<6} {pub_date:<12} {stale_after:<8} {src}")

    lines.append(sep)
    lines.append("說明：無即時自動接口之官方年報如實標註為 [STALE]，禁止聲稱即時監測；本模型嚴格落實可追溯與透明紀律。")
    return "\n".join(lines)


def print_single_result(result, verbose: bool = False, scenario: ScenarioData | None = None) -> None:
    sep = "=" * 70
    sub_sep = "-" * 70
    print(sep)
    print(f"WW3 結構風險評估結果: {result.scenario_title} (ID: {result.scenario_id}, 年份: {result.scenario_year})")
    print(sep)
    print(f"  戰爭風險指數 (War Risk Index)     : {result.global_risk_index:.1f} / 100")
    print(f"  危機升級階段 (Escalation Stage)   : {result.stage.title} (Stage {result.stage.stage_number})")
    print(f"  階段詳細定義                      : {result.stage.description}")
    print(sub_sep)
    print("  五層結構分數明細 (Structural Layers):")
    for lid, score in result.layer_scores.items():
        weight = result.layer_weights.get(lid, 1.0)
        print(f"    - [{lid}] 得分: {score:5.1f} / 100  (權重: {weight:.1f})")
    print(f"  基礎結構加權分 (Base Structural)  : {result.base_structural_score:.1f} / 100")
    print(sub_sep)
    print("  和平機制閘門 (Peace Mechanism Gate):")
    print(f"    - 和平機制容量 (Peace Capacity) : {result.peace_capacity:.1f} / 100")
    print(f"    - 機制失效度 (Gate Failure)     : {result.gate_failure:.1f} / 100")
    print(f"    - 閘門乘數 (Gate Factor)        : x{result.gate_factor:.3f}")
    print(sub_sep)
    print("  互動效應加成 (Interaction Effects):")
    print(f"    - L1 × L2 (資源短缺 × 分配不均) : +{result.interactions['L1_x_L2']:.2f}")
    print(f"    - L3 × L5 (失業AI × 未來悲觀)   : +{result.interactions['L3_x_L5']:.2f}")
    print(f"    - L4 × 閘門 (安全困境 × 機制失效): +{result.interactions['L4_x_GateFailure']:.2f}")
    print(f"    - 互動總加成 (Total Bonus)      : +{result.interactions['total']:.2f} {'(已達上限)' if result.interactions.get('is_capped') else ''}")
    print(sub_sep)
    print("  結構風險情境帶（非經驗證概率） (Scenario Structural Risk Bands):")
    print("    [結構風險之情境推演估算，非已驗證統計預測；大國全面戰爭歷史基率極低，結構指數係易燃度而非事件機率]")
    for hid in ["1y", "5y", "10y"]:
        b = result.probability_bands[hid]
        print(f"    - {b.horizon_years:2d} 年期: {b.lower_pct:4.1f}% – {b.upper_pct:4.1f}%  (中位: {b.central_pct:4.1f}%)")
    print(sub_sep)
    print("  前三大推動風險指標 (Top Risk Pushers):")
    for i, drv in enumerate(result.top_risk_drivers[:3], 1):
        print(f"    {i}. [{drv['layer']}] {drv['name']} ({drv['id']}): {drv['value']:.1f}/100")

    if scenario is not None:
        q = scenario.calculate_data_quality()
        print(sub_sep)
        print(f"  數據品質快訊 (Data Quality)       : 完整度 {q['completeness_pct']:.1f}% | 狀態: Fresh {q['fresh_count']} / Stale {q['stale_count']} / Missing {q['missing_count']}")
    print(sep)


def run_historical(historical_path: str | Path, model: WW3RiskModel, as_json: bool = False) -> None:
    path = Path(historical_path)
    if not path.exists():
        print(f"Error: Historical cases file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scenarios: List[ScenarioData] = []
    cases = data if isinstance(data, list) else data.get("cases", [])
    for c in cases:
        scenarios.append(ScenarioData.from_dict(c))

    results = compare_scenarios(scenarios, model=model)
    # Sort by risk index descending
    results.sort(key=lambda r: r.global_risk_index, reverse=True)

    if as_json:
        print(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
        return

    print("\n歷史案例結構風險排序 (Historical Cases Ranking):")
    print(format_comparison_ascii_table(results))
    print()


def main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ww3-risk",
        description="WW3 Risk Model — Five-layer structural risk index with peace gate, interactions, and data quality tracking",
    )
    parser.add_argument("--scenario", "-s", type=str, help="Path to scenario JSON file")
    parser.add_argument("--compare", "-c", nargs="+", help="Paths or globs of scenario JSON files to compare")
    parser.add_argument("--historical", "-H", type=str, help="Path to historical_cases.json")
    parser.add_argument("--report", "-r", type=str, help="Path to output Markdown report")
    parser.add_argument("--dashboard", "-d", type=str, help="Path to generate static dashboard HTML")
    parser.add_argument("--export-snapshot", type=str, help="Export D1-compatible baseline calculation snapshot JSON")
    parser.add_argument("--data-quality", "-q", action="store_true", help="Output comprehensive data quality and staleness report")
    parser.add_argument("--as-of-date", type=str, default="2026-10-21", help="Reference date for staleness evaluation (YYYY-MM-DD)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON format")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show verbose indicator output")

    parsed = parser.parse_args(args)

    model = WW3RiskModel()

    # Case 0: Data quality report
    if parsed.data_quality:
        scenario_file = Path(parsed.scenario) if parsed.scenario else Path("scenarios/baseline_2026.json")
        if not scenario_file.exists():
            scenario_file = Path("data/baseline_2026.json")
        if not scenario_file.exists():
            print(f"Error: Baseline scenario file not found: {scenario_file}", file=sys.stderr)
            sys.exit(1)

        scenario = load_scenario_from_file(scenario_file)
        quality = scenario.calculate_data_quality(as_of_date=parsed.as_of_date)

        if parsed.json:
            print(json.dumps(quality, ensure_ascii=False, indent=2))
        else:
            print(format_data_quality_report(quality))
        return

    # Case 0.5: Export D1 snapshot JSON
    if parsed.export_snapshot:
        scenario_file = Path(parsed.scenario) if parsed.scenario else Path("scenarios/baseline_2026.json")
        if not scenario_file.exists():
            scenario_file = Path("data/baseline_2026.json")
        if not scenario_file.exists():
            print(f"Error: Baseline scenario file not found: {scenario_file}", file=sys.stderr)
            sys.exit(1)

        scenario = load_scenario_from_file(scenario_file)
        snap = export_snapshot_to_file(
            output_path=parsed.export_snapshot,
            scenario=scenario,
            model=model,
            as_of_date=parsed.as_of_date,
        )
        print(f"D1 快照 JSON 已導出: {parsed.export_snapshot} (Snapshot ID: {snap['snapshot']['id']}, 指標數: {len(snap['observations'])})")
        return

    # Case 1: Historical comparison
    if parsed.historical:
        run_historical(parsed.historical, model=model, as_json=parsed.json)
        return

    # Case 2: Compare multiple scenarios
    if parsed.compare:
        files: List[Path] = []
        for pattern in parsed.compare:
            matched = glob.glob(pattern)
            if matched:
                files.extend(Path(p) for p in sorted(matched))
            else:
                files.append(Path(pattern))

        scenarios: List[ScenarioData] = []
        for file_path in files:
            if not file_path.exists():
                print(f"Warning: File not found: {file_path}", file=sys.stderr)
                continue
            scenarios.append(load_scenario_from_file(file_path))

        if not scenarios:
            print("Error: No valid scenarios loaded for comparison.", file=sys.stderr)
            sys.exit(1)

        results = compare_scenarios(scenarios, model=model)

        if parsed.json:
            print(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
        else:
            print("\n情境對比分析 (Scenario Comparison):")
            print(format_comparison_ascii_table(results))
            print()

        if parsed.report:
            report_lines = [
                "# WW3 結構風險多情境對比報告",
                "",
                "## 情境對比總表",
                "",
                format_comparison_ascii_table(results),
                "",
            ]
            for r in results:
                report_lines.append(generate_markdown_report(r))
                report_lines.append("\n---\n")
            with open(parsed.report, "w", encoding="utf-8") as f:
                f.write("\n".join(report_lines))
            print(f"對比報告已寫入: {parsed.report}")
        return

    # Case 3: Single scenario evaluation
    if parsed.scenario:
        scenario_path = Path(parsed.scenario)
        if not scenario_path.exists():
            print(f"Error: Scenario file not found: {scenario_path}", file=sys.stderr)
            sys.exit(1)

        scenario = load_scenario_from_file(scenario_path)
        result = model.evaluate(scenario)

        if parsed.json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print_single_result(result, verbose=parsed.verbose, scenario=scenario)

        if parsed.report:
            md_content = generate_markdown_report(result)
            with open(parsed.report, "w", encoding="utf-8") as f:
                f.write(md_content)
            print(f"分析報告已儲存至: {parsed.report}")

        if parsed.dashboard:
            build_dashboard(scenario_path=scenario_path, output_html_path=parsed.dashboard, model=model)
            print(f"靜態儀表板 HTML 已生成: {parsed.dashboard}")
        return

    # Case 4: Dashboard generation standalone without --scenario (defaults to baseline)
    if parsed.dashboard:
        default_scenario = Path("scenarios/baseline_2026.json")
        build_dashboard(scenario_path=default_scenario, output_html_path=parsed.dashboard, model=model)
        print(f"靜態儀表板 HTML 已生成: {parsed.dashboard}")
        return

    # Default if no arguments provided
    parser.print_help()


if __name__ == "__main__":
    main()
