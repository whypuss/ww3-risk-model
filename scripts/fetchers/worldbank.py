#!/usr/bin/env python3
"""World Bank Open Data Fetcher for WW3 Risk Model Indicators.

Retrieves macroeconomic and geopolitical structural series via World Bank API v2.
Outputs candidates solely to data/candidates/worldbank_candidates.json.
ABSOLUTELY NEVER OVERWRITES data/baseline_2026.json.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


WB_SERIES_DEFINITIONS = [
    {
        "wb_code": "MS.MIL.XPND.GD.ZS",
        "wb_name": "Military expenditure (% of GDP)",
        "country": "WLD",
        "target_indicator_id": "l4_military_expenditure_growth",
        "target_indicator_name": "全球軍費實質增長率與GDP佔比",
        "applicability_rationale": "世銀全球軍費佔GDP比率提供全球宏觀軍事化負擔之客觀量化基準，反映體系資源轉移至安全困境之程度。",
    },
    {
        "wb_code": "SL.UEM.TOTL.ZS",
        "wb_name": "Unemployment, total (% of total labor force)",
        "country": "WLD",
        "target_indicator_id": "l3_unemployment_underemployment",
        "target_indicator_name": "全球結構性失業與不充分就業率",
        "applicability_rationale": "ILO/World Bank全球總體失業率統計，提供勞工階層就業脆弱度基礎實數，衡量經濟邊緣化潛力。",
    },
    {
        "wb_code": "SL.UEM.1524.ZS",
        "wb_name": "Unemployment, youth total (% of total labor force ages 15-24)",
        "country": "WLD",
        "target_indicator_id": "l3_youth_unemployment",
        "target_indicator_name": "青年失業率與社會挫折階層規模",
        "applicability_rationale": "15-24歲青年失業率直接對應社會動員挫折感與衝突激化潛在群體規模。",
    },
    {
        "wb_code": "EG.USE.COMM.FO.ZS",
        "wb_name": "Fossil fuel energy consumption (% of total)",
        "country": "WLD",
        "target_indicator_id": "l1_energy_vulnerability",
        "target_indicator_name": "化石能源與電網供應鏈脆弱性",
        "applicability_rationale": "全球化石能源消費佔比反映對碳氫化合物戰略航道（霍爾木茲/曼德海峽）之剛性依賴度。",
    },
    {
        "wb_code": "SI.POV.GINI",
        "wb_name": "Gini index",
        "country": "WLD",
        "target_indicator_id": "l2_wealth_gini",
        "target_indicator_name": "全球前 1% 財富佔有率與跨國基尼系數",
        "applicability_rationale": "世銀跨國基尼系數反映財富與收入分配不平等宏觀趨勢，對應體系內部與跨國分配正義裂痕。",
    },
]


def fetch_worldbank_indicator(
    indicator_code: str,
    country: str = "WLD",
    date_range: str = "2018:2026",
    timeout: int = 15,
) -> Optional[Dict[str, Any]]:
    """Fetch time series data from World Bank API v2."""
    url = f"http://api.worldbank.org/v2/country/{country}/indicator/{indicator_code}?format=json&date={date_range}&per_page=15"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ww3-risk-fetcher/0.4.0",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, list) or len(data) < 2 or not data[1]:
                return None

            records = data[1]
            # Find the most recent record with a non-null value
            for r in records:
                if r.get("value") is not None:
                    return {
                        "indicator_id": r.get("indicator", {}).get("id", indicator_code),
                        "indicator_value": r.get("indicator", {}).get("value", ""),
                        "country_id": r.get("country", {}).get("id", country),
                        "country_value": r.get("country", {}).get("value", ""),
                        "year": str(r.get("date", "")),
                        "value": float(r.get("value")),
                        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
            return None
    except Exception as e:
        # Return none on failure or timeout; callers handle gracefully
        return None


def run_worldbank_fetcher(
    baseline_path: str | Path = "data/baseline_2026.json",
    output_path: str | Path = "data/candidates/worldbank_candidates.json",
    dry_run: bool = False,
    mock_responses: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Execute World Bank series fetch and generate candidates report."""
    baseline_p = Path(baseline_path)
    output_p = Path(output_path)

    # STRICT SANITY CHECK: Absolutely never overwrite baseline
    if output_p.resolve() == baseline_p.resolve():
        raise ValueError(
            f"FATAL: Attempted to overwrite baseline '{baseline_p}' with candidate output! Aborting."
        )

    current_indicators: Dict[str, Any] = {}
    if baseline_p.exists():
        with open(baseline_p, "r", encoding="utf-8") as f:
            bdata = json.load(f)
            # Flatten layer indicators
            for layer in bdata.get("layers", {}).values():
                for ind in layer.get("indicators", []):
                    current_indicators[ind["id"]] = ind

    candidates: List[Dict[str, Any]] = []

    for item in WB_SERIES_DEFINITIONS:
        wb_code = item["wb_code"]
        target_id = item["target_indicator_id"]

        wb_res: Optional[Dict[str, Any]] = None
        if mock_responses and wb_code in mock_responses:
            wb_res = mock_responses[wb_code]
        elif not dry_run:
            wb_res = fetch_worldbank_indicator(wb_code, country=item["country"])

        curr = current_indicators.get(target_id, {})
        curr_raw = curr.get("raw_value")
        curr_norm = curr.get("normalized_score", curr.get("value"))

        candidate_entry = {
            "wb_code": wb_code,
            "wb_name": item["wb_name"],
            "target_indicator_id": target_id,
            "target_indicator_name": item["target_indicator_name"],
            "applicability_rationale": item["applicability_rationale"],
            "candidate_year": wb_res.get("year") if wb_res else None,
            "candidate_raw_value": wb_res.get("value") if wb_res else None,
            "current_model_raw_value": curr_raw,
            "current_model_score": curr_norm,
            "current_evidence_level": curr.get("evidence_level", "illustrative"),
            "fetch_status": "success" if wb_res else ("dry_run" if dry_run else "fetch_failed_or_empty"),
            "diff_analysis": (
                f"Candidate WB value: {wb_res['value']} ({wb_res['year']}) vs. current baseline: {curr_raw} (score: {curr_norm})"
                if wb_res
                else "No remote value retrieved; baseline unchanged."
            ),
        }
        candidates.append(candidate_entry)

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "World Bank Open Data API v2 (api.worldbank.org)",
        "disclaimer": "Candidate values generated for expert review. Not applied to baseline without manual rubric calibration.",
        "series_count": len(candidates),
        "candidates": candidates,
    }

    if not dry_run:
        output_p.parent.mkdir(parents=True, exist_ok=True)
        with open(output_p, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch World Bank indicators for WW3 Risk Model")
    parser.add_argument("--baseline", type=str, default="data/baseline_2026.json", help="Path to baseline scenario JSON")
    parser.add_argument("--output", type=str, default="data/candidates/worldbank_candidates.json", help="Path to write candidates JSON")
    parser.add_argument("--dry-run", action="store_true", help="Preview series mappings without making HTTP requests")

    args = parser.parse_args()
    report = run_worldbank_fetcher(
        baseline_path=args.baseline,
        output_path=args.output,
        dry_run=args.dry_run,
    )
    print(f"World Bank Candidates Report ({report['series_count']} series) generated at: {args.output}")
    for c in report["candidates"]:
        print(f"  - [{c['target_indicator_id']}] {c['wb_code']}: {c['fetch_status']} (Candidate: {c['candidate_raw_value']} / Current: {c['current_model_raw_value']})")


if __name__ == "__main__":
    main()
