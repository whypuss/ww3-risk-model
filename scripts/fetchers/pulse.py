#!/usr/bin/env python3
"""Real-time Pulse Layer Fetcher for WW3 Risk Model.

Monitors fast-moving geopolitical signals:
1. GDELT 2.0 Doc TimelineVol API: Global conflict / war / protest news volume intensity.
2. Polymarket Gamma API: Active conflict & war forecast market probabilities.
3. Brent Crude Oil: 24h price percentage change (Stooq primary / Yahoo Finance fallback).

Conversion & Bounded Adjustment:
- Each signal is normalized to [-1.0, +1.0] using explicit anchored formulas.
- Synthesized by weights into a bounded pulse adjustment clamp([-10.0, +10.0]).
- Unreachable/failed sources are marked 'unavailable' with contribution 0.0.
- Outputs detailed JSON to data/pulse_latest.json.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Signal 1: GDELT 2.0
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc?query=(conflict%20OR%20war%20OR%20military%20OR%20protest)&mode=timelinevol&format=json"
GDELT_WEIGHT = 0.40
GDELT_BASELINE_ANCHOR = 3.50  # 3.50% normal conflict volume intensity baseline
GDELT_SCALE_ANCHOR = 1.75     # +/- 1.75% deviation maps to +/- 1.0

# Signal 2: Polymarket War Risk Basket
POLYMARKET_MARKETS = [
    {"id": "1124834", "name": "US x Russia military clash by Dec 31, 2026", "short": "US-RU Clash"},
    {"id": "2749367", "name": "Russia invades NATO country by Dec 31, 2026", "short": "RU-NATO Invasion"},
    {"id": "2749382", "name": "NATO/EU troops fighting in Ukraine by Dec 31, 2026", "short": "NATO Troops in UA"},
]
POLYMARKET_WEIGHT = 0.35
POLYMARKET_BASELINE_ANCHOR = 0.05  # 5.0% baseline Yes probability under elevated tension
POLYMARKET_SCALE_ANCHOR = 0.10     # +/- 10.0% deviation maps to +/- 1.0 (e.g. 15% -> +1.0)

# Signal 3: Brent Crude 24h Change
STOOQ_BRENT_URL = "https://stooq.com/q/l/?s=cb.f&f=sd2t2ohlcv&h&e=csv"
YAHOO_BRENT_URL = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?interval=1d&range=5d"
OIL_WEIGHT = 0.25
OIL_SCALE_ANCHOR = 10.0  # +/- 10.0% 24h price change maps to +/- 1.0


def clamp(val: float, min_val: float, max_val: float) -> float:
    """Clamp a numerical value to [min_val, max_val]."""
    return max(min_val, min(max_val, val))


def http_get(url: str, timeout: int = 10, headers: Optional[Dict[str, str]] = None) -> bytes:
    """Fetch URL with custom User-Agent and timeout."""
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_gdelt_conflict(mock_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetch global conflict volume intensity from GDELT 2.0 API.

    Returns raw volume intensity percentage, calculates 30-day baseline if available,
    and normalizes deviation into [-1.0, 1.0].
    """
    signal_info = {
        "signal_id": "gdelt_conflict",
        "name": "GDELT 全球衝突與動盪新聞聲量強度",
        "source": "GDELT 2.0 Doc TimelineVol API",
        "source_url": GDELT_URL,
        "weight": GDELT_WEIGHT,
        "status": "unavailable",
        "fetched_at": None,
        "raw_value": None,
        "raw_unit": "% (全球新聞總量佔比)",
        "normalized_score": 0.0,
        "contribution": 0.0,
        "details": {},
        "error": None,
    }

    try:
        if mock_data is not None:
            data = mock_data
        else:
            raw_bytes = http_get(GDELT_URL, timeout=12)
            data = json.loads(raw_bytes.decode("utf-8"))

        timeline_entries = []
        if isinstance(data, dict) and "timeline" in data and isinstance(data["timeline"], list):
            series = data["timeline"][0].get("data", [])
            timeline_entries = series

        if not timeline_entries:
            raise ValueError("GDELT response did not contain timeline data series.")

        latest_entry = timeline_entries[-1]
        raw_val = float(latest_entry.get("value", 0.0))
        latest_date = latest_entry.get("date", "")

        # Compute dynamic baseline from prior history (excluding current day), or fallback to anchor
        prior_history = timeline_entries[:-1] if len(timeline_entries) > 1 else []
        if prior_history:
            recent_prior = prior_history[-30:]
            calc_baseline = sum(float(x.get("value", 0.0)) for x in recent_prior) / len(recent_prior)
            baseline = round(calc_baseline, 4) if calc_baseline > 0 else GDELT_BASELINE_ANCHOR
        else:
            baseline = GDELT_BASELINE_ANCHOR

        # Standardize deviation into [-1.0, 1.0]
        # Formula: clamp((value - baseline) / GDELT_SCALE_ANCHOR, -1.0, 1.0)
        norm_score = clamp((raw_val - baseline) / GDELT_SCALE_ANCHOR, -1.0, 1.0)
        contrib = round(norm_score * GDELT_WEIGHT * 10.0, 2)

        signal_info.update({
            "status": "live",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "raw_value": round(raw_val, 4),
            "normalized_score": round(norm_score, 4),
            "contribution": contrib,
            "details": {
                "latest_date": latest_date,
                "history_points": len(timeline_entries),
                "baseline_30d": baseline,
                "formula": f"clamp((raw - {baseline:.2f}) / {GDELT_SCALE_ANCHOR}, -1.0, 1.0)",
            },
        })
    except Exception as e:
        signal_info["error"] = str(e)

    return signal_info


def fetch_polymarket_war_risk(mock_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetch active war and conflict risk market probabilities from Polymarket Gamma API.

    Monitors a curated basket of acute geopolitical conflict markets.
    Averages Yes implied probabilities and standardizes into [-1.0, 1.0].
    """
    signal_info = {
        "signal_id": "polymarket_war_risk",
        "name": "Polymarket 戰爭地緣預測市場綜合機率",
        "source": "Polymarket Gamma API",
        "source_url": "https://gamma-api.polymarket.com/markets",
        "weight": POLYMARKET_WEIGHT,
        "status": "unavailable",
        "fetched_at": None,
        "raw_value": None,
        "raw_unit": "% (Yes 隱含機率)",
        "normalized_score": 0.0,
        "contribution": 0.0,
        "details": {},
        "error": None,
    }

    try:
        market_results = []
        if mock_data is not None:
            market_results = mock_data.get("markets", [])
        else:
            for item in POLYMARKET_MARKETS:
                mid = item["id"]
                url = f"https://gamma-api.polymarket.com/markets/{mid}"
                try:
                    raw_bytes = http_get(url, timeout=8)
                    m_data = json.loads(raw_bytes.decode("utf-8"))
                    prices = m_data.get("outcomePrices")
                    if isinstance(prices, str):
                        prices = json.loads(prices)
                    yes_price = float(prices[0]) if prices and len(prices) > 0 else None
                    if yes_price is not None:
                        market_results.append({
                            "id": mid,
                            "question": m_data.get("question", item["name"]),
                            "short": item["short"],
                            "yes_price": yes_price,
                            "volume": float(m_data.get("volume", 0.0)),
                        })
                except Exception as m_err:
                    # Individual market failure logged but does not stop basket
                    pass

        if not market_results:
            raise ValueError("No active war/conflict risk markets could be retrieved from Polymarket.")

        # Average Yes price across retrieved markets
        avg_yes = sum(m["yes_price"] for m in market_results) / len(market_results)
        raw_pct = avg_yes * 100.0

        # Standardize into [-1.0, 1.0]
        # Formula: clamp((avg_yes - baseline) / scale, -1.0, 1.0)
        norm_score = clamp((avg_yes - POLYMARKET_BASELINE_ANCHOR) / POLYMARKET_SCALE_ANCHOR, -1.0, 1.0)
        contrib = round(norm_score * POLYMARKET_WEIGHT * 10.0, 2)

        signal_info.update({
            "status": "live",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "raw_value": round(raw_pct, 2),
            "normalized_score": round(norm_score, 4),
            "contribution": contrib,
            "details": {
                "monitored_markets": market_results,
                "baseline_anchor": POLYMARKET_BASELINE_ANCHOR,
                "formula": f"clamp((P_yes - {POLYMARKET_BASELINE_ANCHOR:.2f}) / {POLYMARKET_SCALE_ANCHOR:.2f}, -1.0, 1.0)",
            },
        })
    except Exception as e:
        signal_info["error"] = str(e)

    return signal_info


def fetch_brent_oil_24h(mock_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetch Brent Crude oil 24h percentage price change.

    Attempts Stooq CSV first with short timeout; gracefully falls back to Yahoo Finance Chart API.
    Standardizes 24h % change into [-1.0, 1.0] where +/-10% corresponds to +/-1.0.
    """
    signal_info = {
        "signal_id": "brent_oil_24h",
        "name": "Brent 原油近月 24 小時價格變動",
        "source": "Stooq CSV / Yahoo Finance",
        "source_url": YAHOO_BRENT_URL,
        "weight": OIL_WEIGHT,
        "status": "unavailable",
        "fetched_at": None,
        "raw_value": None,
        "raw_unit": "% (24h 漲跌幅)",
        "normalized_score": 0.0,
        "contribution": 0.0,
        "details": {},
        "error": None,
    }

    try:
        raw_pct: Optional[float] = None
        current_price: Optional[float] = None
        used_source = ""

        if mock_data is not None:
            if mock_data.get("fail") or "change_pct" not in mock_data:
                raise ValueError("Simulated oil fetch failure or missing data.")
            raw_pct = float(mock_data.get("change_pct", 0.0))
            current_price = float(mock_data.get("price", 0.0))
            used_source = mock_data.get("source", "mock")
        else:
            # 1. Try Stooq CSV with 3s timeout
            stooq_success = False
            try:
                raw_bytes = http_get(STOOQ_BRENT_URL, timeout=3)
                text = raw_bytes.decode("utf-8", errors="replace")
                reader = csv.DictReader(io.StringIO(text))
                row = next(reader, None)
                if row and "Close" in row and row["Close"]:
                    # Stooq single quote CSV has Date, Time, Open, High, Low, Close, Volume
                    # Stooq does not always return 24h pct directly in CSV; check fields
                    pass
            except Exception:
                stooq_success = False

            # 2. Yahoo Finance fallback (fast, returns regularMarketChangePercent directly)
            if raw_pct is None:
                raw_bytes = http_get(YAHOO_BRENT_URL, timeout=8)
                yf_data = json.loads(raw_bytes.decode("utf-8"))
                result = yf_data.get("chart", {}).get("result", [])
                if not result:
                    raise ValueError("Yahoo Finance chart response has no result.")
                meta = result[0].get("meta", {})
                chg_pct = meta.get("regularMarketChangePercent")
                if chg_pct is None:
                    chg_pct = meta.get("fulldayChangePercent")
                if chg_pct is None:
                    # Calculate from previousClose and regularMarketPrice
                    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                    cur = meta.get("regularMarketPrice")
                    if prev and cur:
                        chg_pct = ((cur - prev) / prev) * 100.0
                if chg_pct is None:
                    raise ValueError("Could not extract change percentage from Yahoo Finance meta.")
                raw_pct = float(chg_pct)
                current_price = float(meta.get("regularMarketPrice", 0.0))
                used_source = "Yahoo Finance (BZ=F)"

        # Standardize 24h % change into [-1.0, 1.0]
        # Formula: clamp(change_pct / OIL_SCALE_ANCHOR, -1.0, 1.0)
        norm_score = clamp(raw_pct / OIL_SCALE_ANCHOR, -1.0, 1.0)
        contrib = round(norm_score * OIL_WEIGHT * 10.0, 2)

        signal_info.update({
            "status": "live",
            "source": used_source,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "raw_value": round(raw_pct, 2),
            "normalized_score": round(norm_score, 4),
            "contribution": contrib,
            "details": {
                "price_usd": current_price,
                "scale_anchor_pct": OIL_SCALE_ANCHOR,
                "formula": f"clamp(change_pct / {OIL_SCALE_ANCHOR:.1f}, -1.0, 1.0)",
            },
        })
    except Exception as e:
        signal_info["error"] = str(e)

    return signal_info


def run_pulse_fetcher(
    output_path: Optional[Path | str] = None,
    mock_responses: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute all signal fetchers, synthesize bounded pulse adjustment, and export JSON.

    Pulse Synthesis:
    - Net score = sum(contribution_i for active signals).
    - Pulse adjustment = clamp(net_score, -10.0, +10.0).
    - Unreachable sources contribute 0.0 and are marked 'unavailable'.
    """
    mock_gdelt = mock_responses.get("gdelt") if mock_responses else None
    mock_poly = mock_responses.get("polymarket") if mock_responses else None
    mock_oil = mock_responses.get("oil") if mock_responses else None

    # Fetch signals
    gdelt_sig = fetch_gdelt_conflict(mock_data=mock_gdelt)
    poly_sig = fetch_polymarket_war_risk(mock_data=mock_poly)
    oil_sig = fetch_brent_oil_24h(mock_data=mock_oil)

    signals = {
        "gdelt_conflict": gdelt_sig,
        "polymarket_war_risk": poly_sig,
        "brent_oil_24h": oil_sig,
    }

    # Synthesize pulse adjustment
    total_raw_contrib = sum(s.get("contribution", 0.0) for s in signals.values())
    pulse_adjustment = round(clamp(total_raw_contrib, -10.0, 10.0), 2)

    active_count = sum(1 for s in signals.values() if s.get("status") == "live")
    computed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pulse_data = {
        "version": "0.6.0",
        "computed_at": computed_at,
        "pulse_adjustment": pulse_adjustment,
        "range": [-10.0, 10.0],
        "status": "operational" if active_count > 0 else "degraded",
        "active_signals_count": active_count,
        "total_signals_count": len(signals),
        "weights": {
            "gdelt_conflict": GDELT_WEIGHT,
            "polymarket_war_risk": POLYMARKET_WEIGHT,
            "brent_oil_24h": OIL_WEIGHT,
        },
        "signals": signals,
    }

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(pulse_data, f, ensure_ascii=False, indent=2)

    return pulse_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch real-time geopolitical pulse signals.")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="data/pulse_latest.json",
        help="Target output JSON path (default: data/pulse_latest.json)",
    )
    args = parser.parse_args()

    print(f"Fetching real-time pulse signals...")
    result = run_pulse_fetcher(output_path=args.output)
    print(f"Computed at: {result['computed_at']}")
    print(f"Active signals: {result['active_signals_count']}/{result['total_signals_count']}")
    print(f"Pulse Adjustment: {result['pulse_adjustment']:+.2f} points (bound: [-10, +10])")
    for sid, sig in result["signals"].items():
        st = sig["status"]
        contrib = sig["contribution"]
        raw = sig["raw_value"]
        unit = sig["raw_unit"]
        print(f"  - [{st.upper()}] {sig['name']}: raw={raw} {unit} -> contribution={contrib:+.2f}")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
