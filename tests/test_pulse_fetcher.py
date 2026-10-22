"""Unit tests for Real-time Pulse Layer Fetcher and Bounded Synthesis.

Strict requirement: All tests use mock fixtures with ZERO network calls.
Tests cover:
- Standard calculation with fixed mock fixtures -> exact normalized scores and contributions
- Clamp bounds [-10.0, +10.0] on extreme outlier inputs
- Complete source outage (all sources fail) -> pulse=0.0 and all marked unavailable
- Partial outage (single or two sources fail) -> remaining signals calculated correctly
- File export integrity and data schema consistency
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.fetchers.pulse import (
    run_pulse_fetcher,
    fetch_gdelt_conflict,
    fetch_polymarket_war_risk,
    fetch_brent_oil_24h,
    clamp,
    GDELT_WEIGHT,
    POLYMARKET_WEIGHT,
    OIL_WEIGHT,
)


@pytest.fixture
def standard_mock_data():
    """Standard realistic fixture for the 3 pulse signals."""
    return {
        "gdelt": {
            "timeline": [
                {
                    "data": [
                        {"date": f"202610{i:02d}", "value": 3.50}
                        for i in range(1, 20)
                    ] + [
                        {"date": "20261021", "value": 4.375}  # +0.875 over baseline
                    ]
                }
            ]
        },
        "polymarket": {
            "markets": [
                {"id": "1124834", "question": "US x Russia", "short": "US-RU", "yes_price": 0.08, "volume": 100000.0},
                {"id": "2749367", "question": "Russia NATO", "short": "RU-NATO", "yes_price": 0.12, "volume": 100000.0},
            ]
            # avg_yes = 0.10 (10.0%) -> deviation = (0.10 - 0.05) / 0.10 = +0.50
        },
        "oil": {
            "change_pct": 5.0,  # +5% 24h change -> deviation = 5.0 / 10.0 = +0.50
            "price": 85.0,
            "source": "Mock Oil",
        },
    }


def test_standard_pulse_calculation(standard_mock_data, tmp_path):
    """Verify standard formula calculations, weights, and contributions."""
    out_file = tmp_path / "pulse_latest.json"
    result = run_pulse_fetcher(output_path=out_file, mock_responses=standard_mock_data)

    assert out_file.exists()
    assert result["version"] == "0.6.0"
    assert result["status"] == "operational"
    assert result["active_signals_count"] == 3
    assert result["total_signals_count"] == 3

    sigs = result["signals"]
    # 1. GDELT:
    # baseline = 3.50. Latest = 4.375. Diff = +0.875. Scale = 1.75. Norm = 0.875 / 1.75 = 0.50
    # Contrib = 0.50 * 0.40 * 10 = +2.00
    gdelt = sigs["gdelt_conflict"]
    assert gdelt["status"] == "live"
    assert gdelt["raw_value"] == 4.375
    assert gdelt["normalized_score"] == pytest.approx(0.50, abs=0.01)
    assert gdelt["contribution"] == pytest.approx(2.00, abs=0.01)

    # 2. Polymarket:
    # avg_yes = 0.10 (10%). Baseline = 0.05. Scale = 0.10. Norm = (0.10 - 0.05) / 0.10 = 0.50
    # Contrib = 0.50 * 0.35 * 10 = +1.75
    poly = sigs["polymarket_war_risk"]
    assert poly["status"] == "live"
    assert poly["raw_value"] == 10.0
    assert poly["normalized_score"] == pytest.approx(0.50, abs=0.01)
    assert poly["contribution"] == pytest.approx(1.75, abs=0.01)

    # 3. Oil:
    # change_pct = +5.0%. Scale = 10.0. Norm = 5.0 / 10.0 = 0.50
    # Contrib = 0.50 * 0.25 * 10 = +1.25
    oil = sigs["brent_oil_24h"]
    assert oil["status"] == "live"
    assert oil["raw_value"] == 5.0
    assert oil["normalized_score"] == pytest.approx(0.50, abs=0.01)
    assert oil["contribution"] == pytest.approx(1.25, abs=0.01)

    # Total pulse adjustment = 2.00 + 1.75 + 1.25 = +5.00
    assert result["pulse_adjustment"] == pytest.approx(5.00, abs=0.02)


def test_extreme_positive_clamp():
    """Verify clamp caps pulse adjustment at +10.0 when signals explode upward."""
    extreme_mocks = {
        "gdelt": {
            "timeline": [{"data": [{"date": "20261001", "value": 3.5}, {"date": "20261022", "value": 50.0}]}]
        },
        "polymarket": {
            "markets": [
                {"id": "1", "question": "War", "short": "War", "yes_price": 0.95, "volume": 1000.0}
            ]
        },
        "oil": {
            "change_pct": 80.0,
            "price": 150.0,
            "source": "Mock Oil",
        },
    }

    result = run_pulse_fetcher(mock_responses=extreme_mocks)
    assert result["signals"]["gdelt_conflict"]["normalized_score"] == 1.0
    assert result["signals"]["polymarket_war_risk"]["normalized_score"] == 1.0
    assert result["signals"]["brent_oil_24h"]["normalized_score"] == 1.0
    # Clamped at exactly +10.0
    assert result["pulse_adjustment"] == 10.0


def test_extreme_negative_clamp():
    """Verify clamp floors pulse adjustment at -10.0 when signals drop to minimum."""
    extreme_negative_mocks = {
        "gdelt": {
            "timeline": [
                {"data": [{"date": f"202610{i:02d}", "value": 4.0} for i in range(1, 10)] + [{"date": "20261022", "value": 0.0}]}
            ]
        },
        "polymarket": {
            "markets": [
                {"id": "1", "question": "War", "short": "War", "yes_price": 0.0, "volume": 1000.0}
            ]
        },
        "oil": {
            "change_pct": -40.0,  # -40% crash
            "price": 40.0,
            "source": "Mock Oil",
        },
    }

    result = run_pulse_fetcher(mock_responses=extreme_negative_mocks)
    # Check clamp logic
    assert result["pulse_adjustment"] >= -10.0
    assert result["pulse_adjustment"] <= 10.0


def test_complete_source_outage_failsafe():
    """Verify that when all sources fail, pulse adjustment is 0.0 and status is marked degraded."""
    outage_mocks = {
        "gdelt": {"timeline": []},    # Empty timeline
        "polymarket": {"markets": []}, # No markets
        "oil": {"fail": True},         # Explicit failure
    }

    result = run_pulse_fetcher(mock_responses=outage_mocks)
    assert result["status"] == "degraded"
    assert result["active_signals_count"] == 0
    assert result["pulse_adjustment"] == 0.0

    for sid, sig in result["signals"].items():
        assert sig["status"] == "unavailable"
        assert sig["raw_value"] is None
        assert sig["normalized_score"] == 0.0
        assert sig["contribution"] == 0.0
        assert sig["error"] is not None


def test_partial_outage_graceful_degradation():
    """Verify that if one source fails (e.g. Polymarket down), others still contribute accurately."""
    partial_mocks = {
        "gdelt": {
            "timeline": [
                {"data": [{"date": "20261021", "value": 3.50}, {"date": "20261022", "value": 4.375}]}
            ]
        },
        "polymarket": {},  # Polymarket down!
        "oil": {
            "change_pct": 5.0,
            "price": 85.0,
            "source": "Mock Oil",
        },
    }

    result = run_pulse_fetcher(mock_responses=partial_mocks)
    assert result["active_signals_count"] == 2
    assert result["signals"]["polymarket_war_risk"]["status"] == "unavailable"
    assert result["signals"]["polymarket_war_risk"]["contribution"] == 0.0

    # GDELT contribution = +2.00, Oil contribution = +1.25 -> Total = +3.25
    assert result["signals"]["gdelt_conflict"]["contribution"] == pytest.approx(2.00, abs=0.01)
    assert result["signals"]["brent_oil_24h"]["contribution"] == pytest.approx(1.25, abs=0.01)
    assert result["pulse_adjustment"] == pytest.approx(3.25, abs=0.02)
