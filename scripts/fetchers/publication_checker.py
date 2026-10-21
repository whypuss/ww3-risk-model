#!/usr/bin/env python3
"""Official Annual Publication Release Checker for WW3 Risk Model.

Monitors authoritative sources (SIPRI, IMF, ILO, FAO, IEA, World Bank) for new releases.
Uses HTTP HEAD/GET metadata (ETag, Last-Modified, content length) to detect updates.
Honest positioning: Detects publication editions, does NOT automatically extract numbers.
Outputs exclusively to data/candidates/publication-check.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


MONITORED_PUBLICATIONS = [
    {
        "id": "sipri_milex",
        "name": "SIPRI Trends in World Military Expenditure",
        "publisher": "Stockholm International Peace Research Institute (SIPRI)",
        "url": "https://www.sipri.org/databases/milex",
        "target_indicators": ["l4_military_expenditure_growth"],
        "expected_cadence": "Annual (Late April)",
        "monitoring_note": "年度全球軍費發布，為模型 L4 軍備擴張權威基準來源。",
    },
    {
        "id": "imf_weo",
        "name": "IMF World Economic Outlook (WEO)",
        "publisher": "International Monetary Fund (IMF)",
        "url": "https://www.imf.org/en/Publications/WEO",
        "target_indicators": ["l5_economic_stagnation", "l4_trade_weaponization"],
        "expected_cadence": "Semi-Annual (April & October)",
        "monitoring_note": "國際貨幣基金組織全球經濟展望，為長期經濟停滯與貿易摩擦來源。",
    },
    {
        "id": "ilo_weso",
        "name": "ILO World Employment and Social Outlook (WESO)",
        "publisher": "International Labour Organization (ILO)",
        "url": "https://www.ilo.org/global/research/global-reports/weso/trends/lang--en/index.htm",
        "target_indicators": ["l3_unemployment_underemployment", "l3_youth_unemployment"],
        "expected_cadence": "Annual (January)",
        "monitoring_note": "國際勞工組織就業年報，為全球結構性與青年失業率權威來源。",
    },
    {
        "id": "fao_food_outlook",
        "name": "FAO Food Outlook & Cereal Supply and Demand",
        "publisher": "Food and Agriculture Organization (FAO)",
        "url": "https://www.fao.org/worldfoodsituation/csdb/en/",
        "target_indicators": ["l1_food_security"],
        "expected_cadence": "Monthly/Quarterly",
        "monitoring_note": "聯合國糧農組織主糧庫存消費比與糧價波動指標監測。",
    },
    {
        "id": "iea_critical_minerals",
        "name": "IEA Global Critical Minerals Outlook",
        "publisher": "International Energy Agency (IEA)",
        "url": "https://www.iea.org/reports/global-critical-minerals-outlook-2024",
        "target_indicators": ["l1_critical_minerals"],
        "expected_cadence": "Annual (May)",
        "monitoring_note": "國際能源署關鍵礦物供應集中度與戰略儲備年報。",
    },
    {
        "id": "wb_gep",
        "name": "World Bank Global Economic Prospects (GEP)",
        "publisher": "World Bank Group",
        "url": "https://www.worldbank.org/en/publication/global-economic-prospects",
        "target_indicators": ["l5_economic_stagnation"],
        "expected_cadence": "Semi-Annual (January & June)",
        "monitoring_note": "世界銀行全球經濟前景，反映新興市場與全球成長長期放緩趨勢。",
    },
]


def check_publication_url(
    url: str,
    timeout: int = 15,
) -> Dict[str, Any]:
    """Perform HTTP HEAD (or fallback GET) request to inspect headers for version detection."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ww3-publication-checker/0.4.0",
        "Accept": "*/*",
    }
    req = urllib.request.Request(url, headers=headers, method="HEAD")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            etag = resp.headers.get("ETag", "").strip("\"'")
            last_modified = resp.headers.get("Last-Modified", "")
            content_length = resp.headers.get("Content-Length", "")
            status_code = resp.status
            return {
                "status_code": status_code,
                "etag": etag,
                "last_modified": last_modified,
                "content_length": content_length,
                "check_method": "HEAD",
                "error": None,
            }
    except urllib.error.HTTPError as e:
        # If HEAD is rejected with 405/403, try minimal GET
        if e.code in (403, 405):
            try:
                get_req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(get_req, timeout=timeout) as resp:
                    # Read only first 4KB to compute partial fingerprint
                    chunk = resp.read(4096)
                    etag = resp.headers.get("ETag", "").strip("\"'")
                    last_modified = resp.headers.get("Last-Modified", "")
                    content_length = resp.headers.get("Content-Length", "")
                    return {
                        "status_code": resp.status,
                        "etag": etag,
                        "last_modified": last_modified,
                        "content_length": content_length,
                        "snippet_hash": hashlib.sha256(chunk).hexdigest()[:16],
                        "check_method": "GET_SNIPPET",
                        "error": None,
                    }
            except Exception as get_err:
                return {
                    "status_code": e.code,
                    "etag": "",
                    "last_modified": "",
                    "content_length": "",
                    "check_method": "FAILED",
                    "error": str(get_err),
                }
        return {
            "status_code": e.code,
            "etag": "",
            "last_modified": "",
            "content_length": "",
            "check_method": "HEAD",
            "error": f"HTTP {e.code}",
        }
    except Exception as e:
        return {
            "status_code": 0,
            "etag": "",
            "last_modified": "",
            "content_length": "",
            "check_method": "ERROR",
            "error": str(e),
        }


def run_publication_checker(
    output_path: str | Path = "data/candidates/publication-check.json",
    dry_run: bool = False,
    mock_results: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Inspect all monitored publications and record state differences."""
    output_p = Path(output_path)

    # Load previous check if available
    previous_map: Dict[str, Dict[str, Any]] = {}
    if output_p.exists():
        try:
            with open(output_p, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
                for item in prev_data.get("publications", []):
                    previous_map[item["id"]] = item
        except Exception:
            previous_map = {}

    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results: List[Dict[str, Any]] = []

    for pub in MONITORED_PUBLICATIONS:
        pub_id = pub["id"]
        prev = previous_map.get(pub_id, {})

        if mock_results and pub_id in mock_results:
            net_info = mock_results[pub_id]
        elif not dry_run:
            net_info = check_publication_url(pub["url"])
        else:
            net_info = {
                "status_code": 200,
                "etag": prev.get("etag", "mock-etag"),
                "last_modified": prev.get("last_modified", "Wed, 01 Jan 2026 00:00:00 GMT"),
                "content_length": prev.get("content_length", "1024"),
                "check_method": "DRY_RUN",
                "error": None,
            }

        # Change detection
        has_new_version = False
        change_reason = "No changes detected"

        if net_info.get("status_code") in (200, 301, 302):
            curr_etag = net_info.get("etag", "")
            prev_etag = prev.get("etag", "")
            curr_lm = net_info.get("last_modified", "")
            prev_lm = prev.get("last_modified", "")

            if prev_etag and curr_etag and prev_etag != curr_etag:
                has_new_version = True
                change_reason = f"ETag changed from '{prev_etag}' to '{curr_etag}'"
            elif prev_lm and curr_lm and prev_lm != curr_lm:
                has_new_version = True
                change_reason = f"Last-Modified changed from '{prev_lm}' to '{curr_lm}'"
            elif not prev:
                change_reason = "Initial baseline check recorded"
        elif net_info.get("error"):
            change_reason = f"Check failed: {net_info['error']}"

        entry = {
            "id": pub_id,
            "name": pub["name"],
            "publisher": pub["publisher"],
            "url": pub["url"],
            "target_indicators": pub["target_indicators"],
            "expected_cadence": pub["expected_cadence"],
            "monitoring_note": pub["monitoring_note"],
            "last_checked": current_time,
            "status_code": net_info.get("status_code"),
            "etag": net_info.get("etag", ""),
            "last_modified": net_info.get("last_modified", ""),
            "content_length": net_info.get("content_length", ""),
            "new_edition_detected": has_new_version,
            "change_reason": change_reason,
        }
        results.append(entry)

    report = {
        "generated_at": current_time,
        "purpose": "Detect new editions of official annual/periodic reports (does NOT auto-extract numerical values).",
        "monitored_count": len(results),
        "updates_detected_count": sum(1 for r in results if r["new_edition_detected"]),
        "publications": results,
    }

    if not dry_run:
        output_p.parent.mkdir(parents=True, exist_ok=True)
        with open(output_p, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Check official publication release updates for WW3 Risk Model")
    parser.add_argument("--output", type=str, default="data/candidates/publication-check.json", help="Path to write check report JSON")
    parser.add_argument("--dry-run", action="store_true", help="Preview check without making HTTP requests")

    args = parser.parse_args()
    report = run_publication_checker(output_path=args.output, dry_run=args.dry_run)
    print(f"Publication Checker Report ({report['monitored_count']} sources) generated at: {args.output}")
    print(f"Updates detected: {report['updates_detected_count']}")
    for p in report["publications"]:
        status_flag = "[NEW VERSION!]" if p["new_edition_detected"] else "[CURRENT]"
        print(f"  - {status_flag} {p['id']}: {p['change_reason']} ({p['url']})")


if __name__ == "__main__":
    main()
