"""Unit tests for C4: World Bank Fetcher and Publication Checker.

Strict requirement: All HTTP requests are mocked. Zero network calls in tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.fetchers.publication_checker import run_publication_checker, MONITORED_PUBLICATIONS
from scripts.fetchers.worldbank import run_worldbank_fetcher, WB_SERIES_DEFINITIONS, fetch_worldbank_indicator


def test_worldbank_fetcher_mocked_execution(tmp_path):
    """Test World Bank fetcher with simulated API responses."""
    out_candidates = tmp_path / "wb_candidates.json"
    baseline_path = Path("data/baseline_2026.json")

    mock_wb_data = {
        "MS.MIL.XPND.GD.ZS": {
            "year": "2024",
            "value": 2.45,
            "indicator_id": "MS.MIL.XPND.GD.ZS",
        },
        "SL.UEM.TOTL.ZS": {
            "year": "2024",
            "value": 5.1,
            "indicator_id": "SL.UEM.TOTL.ZS",
        },
        "SL.UEM.1524.ZS": {
            "year": "2024",
            "value": 14.8,
            "indicator_id": "SL.UEM.1524.ZS",
        },
        "EG.USE.COMM.FO.ZS": {
            "year": "2023",
            "value": 78.4,
            "indicator_id": "EG.USE.COMM.FO.ZS",
        },
        "SI.POV.GINI": {
            "year": "2023",
            "value": 38.5,
            "indicator_id": "SI.POV.GINI",
        },
    }

    report = run_worldbank_fetcher(
        baseline_path=baseline_path,
        output_path=out_candidates,
        mock_responses=mock_wb_data,
    )

    assert out_candidates.exists()
    assert report["series_count"] == len(WB_SERIES_DEFINITIONS)
    assert len(report["candidates"]) == 5

    # Verify each candidate structure
    for c in report["candidates"]:
        assert c["wb_code"] in mock_wb_data
        assert c["fetch_status"] == "success"
        assert c["candidate_raw_value"] is not None
        assert c["current_model_raw_value"] is not None
        assert "diff_analysis" in c
        assert "applicability_rationale" in c

    # Double check that baseline was untouched
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline_data = json.load(f)
    assert baseline_data["id"] == "baseline_2026"


def test_worldbank_fetcher_refuses_to_overwrite_baseline(tmp_path):
    """Verify safety guard: fetcher aborts if output path points to baseline."""
    baseline_path = tmp_path / "baseline_2026.json"
    baseline_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="FATAL: Attempted to overwrite baseline"):
        run_worldbank_fetcher(
            baseline_path=baseline_path,
            output_path=baseline_path,  # Intentionally dangerous target
            dry_run=True,
        )


def test_publication_checker_mocked_detection(tmp_path):
    """Test publication checker version change detection via mocked ETag / Last-Modified."""
    out_file = tmp_path / "pub_check.json"

    # Run 1: Initial baseline recording
    initial_mocks = {
        pub["id"]: {
            "status_code": 200,
            "etag": f"etag-{pub['id']}-v1",
            "last_modified": "Mon, 15 Jan 2026 10:00:00 GMT",
            "content_length": "5000",
            "check_method": "HEAD",
            "error": None,
        }
        for pub in MONITORED_PUBLICATIONS
    }

    report1 = run_publication_checker(output_path=out_file, mock_results=initial_mocks)
    assert out_file.exists()
    assert report1["monitored_count"] == len(MONITORED_PUBLICATIONS)
    assert report1["updates_detected_count"] == 0

    # Run 2: SIPRI and IMF release new versions (changed ETag)
    second_mocks = dict(initial_mocks)
    second_mocks["sipri_milex"] = {
        "status_code": 200,
        "etag": "etag-sipri_milex-v2-NEW",
        "last_modified": "Tue, 21 Apr 2026 08:00:00 GMT",
        "content_length": "5400",
        "check_method": "HEAD",
        "error": None,
    }
    second_mocks["imf_weo"] = {
        "status_code": 200,
        "etag": "etag-imf_weo-v2-NEW",
        "last_modified": "Wed, 22 Apr 2026 12:00:00 GMT",
        "content_length": "8200",
        "check_method": "HEAD",
        "error": None,
    }

    report2 = run_publication_checker(output_path=out_file, mock_results=second_mocks)
    assert report2["updates_detected_count"] == 2

    sipri_entry = next(p for p in report2["publications"] if p["id"] == "sipri_milex")
    assert sipri_entry["new_edition_detected"] is True
    assert "ETag changed" in sipri_entry["change_reason"]

    ilo_entry = next(p for p in report2["publications"] if p["id"] == "ilo_weso")
    assert ilo_entry["new_edition_detected"] is False
