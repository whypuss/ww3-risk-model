"""Unit tests for C2a: D1 schema, snapshot generation, SQLite roundtrip, and push script."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from ww3_risk.indicators import load_scenario_from_file
from ww3_risk.model import WW3RiskModel
from ww3_risk.snapshot import create_snapshot, export_snapshot_to_file


def test_schema_ddl_validity_in_memory_sqlite():
    """Verify that cloudflare/schema.sql executes cleanly in SQLite in-memory."""
    schema_path = Path("cloudflare/schema.sql")
    assert schema_path.exists(), "cloudflare/schema.sql must exist"

    sql = schema_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(sql)
        cursor = conn.cursor()

        # Verify tables created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [row[0] for row in cursor.fetchall()]
        assert "index_snapshots" in tables
        assert "indicator_observations" in tables

        # Verify indexes created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name;")
        indexes = [row[0] for row in cursor.fetchall()]
        assert "idx_snapshots_computed_at" in indexes
        assert "idx_observations_snapshot_id" in indexes
        assert "idx_observations_indicator_id" in indexes
    finally:
        conn.close()


def test_snapshot_structure_integrity():
    """Verify snapshot JSON structure and consistency with baseline model evaluation."""
    scenario = load_scenario_from_file("scenarios/baseline_2026.json")
    model = WW3RiskModel()
    snap_data = create_snapshot(scenario, model=model, computed_at="2026-10-21T14:38:00Z", as_of_date="2026-10-21")

    assert "snapshot" in snap_data
    assert "observations" in snap_data

    snap = snap_data["snapshot"]
    assert snap["scenario_id"] == "baseline_2026"
    assert round(snap["total_index"], 1) == 83.5
    assert snap["stage"] == 3
    assert snap["computed_at"] == "2026-10-21T14:38:00Z"
    assert snap["model_version"] == "0.5.0"

    # Check layers JSON inside snapshot
    layers = json.loads(snap["layers_json"])
    assert set(layers.keys()) == {"L1", "L2", "L3", "L4", "L5"}
    assert round(layers["L1"], 1) == 63.0
    assert round(layers["L2"], 1) == 71.3

    # Check drivers JSON
    drivers = json.loads(snap["drivers_json"])
    assert len(drivers) >= 3

    # Check 36 observations (32 layer indicators + 4 gate buffers)
    obs = snap_data["observations"]
    assert len(obs) == 36
    layers_seen = {o["layer"] for o in obs}
    assert layers_seen == {"L1", "L2", "L3", "L4", "L5", "Gate"}

    for item in obs:
        assert item["snapshot_id"] == snap["id"]
        assert item["indicator_id"]
        assert item["evidence_level"] in {"verified", "inference", "illustrative"}
        assert 0.0 <= item["normalized_score"] <= 100.0
        assert item["is_stale"] in (0, 1)
        assert item["stale_after_days"] > 0


def test_snapshot_sql_insert_and_roundtrip():
    """Insert real snapshot into in-memory SQLite and select back to verify numerical precision."""
    schema_sql = Path("cloudflare/schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_sql)

    scenario = load_scenario_from_file("scenarios/baseline_2026.json")
    model = WW3RiskModel()
    snap_data = create_snapshot(scenario, model=model, computed_at="2026-10-21T14:38:00Z")

    # Import helper from push_snapshot
    from scripts.push_snapshot import build_sql_statements

    (snap_sql, snap_params), obs_statements = build_sql_statements(snap_data)

    with conn:
        conn.execute(snap_sql, snap_params)
        for sql, params in obs_statements:
            conn.execute(sql, params)

    cursor = conn.cursor()

    # Query snapshot
    cursor.execute("SELECT id, scenario_id, total_index, stage, layers_json, band_1y, band_5y, band_10y FROM index_snapshots")
    row = cursor.fetchone()
    assert row is not None
    assert row[1] == "baseline_2026"
    assert round(row[2], 1) == 83.5
    assert row[3] == 3
    layers_back = json.loads(row[4])
    assert round(layers_back["L4"], 1) == 75.5
    assert round(layers_back["L3"], 1) == 65.8

    # Query observations count and staleness
    cursor.execute("SELECT COUNT(*), SUM(is_stale) FROM indicator_observations WHERE snapshot_id = ?", (row[0],))
    total_count, stale_count = cursor.fetchone()
    assert total_count == 36
    assert stale_count > 0

    # Query specific indicator
    cursor.execute(
        "SELECT indicator_id, layer, normalized_score, evidence_level FROM indicator_observations WHERE indicator_id = 'l1_food_security'"
    )
    obs_row = cursor.fetchone()
    assert obs_row is not None
    assert obs_row[0] == "l1_food_security"
    assert obs_row[1] == "L1"
    assert obs_row[2] == 52.0
    assert obs_row[3] == "inference"

    conn.close()


def test_cli_export_snapshot_flag(tmp_path):
    """Test --export-snapshot CLI flag."""
    import os
    out_file = tmp_path / "snapshot_cli.json"
    root_dir = Path(__file__).parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root_dir / "src")

    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "ww3_risk.cli",
            "--scenario",
            "scenarios/baseline_2026.json",
            "--export-snapshot",
            str(out_file),
        ],
        capture_output=True,
        text=True,
        cwd=root_dir,
        env=env,
    )
    assert res.returncode == 0, f"CLI failed: {res.stderr}"
    assert out_file.exists()

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "snapshot" in data
    assert "observations" in data
    assert len(data["observations"]) == 36
    assert round(data["snapshot"]["total_index"], 1) == 83.5


def test_sql_statement_parameter_limit_regression():
    """Regression test: Ensure all generated SQL statements have <= 90 parameters.

    Cloudflare D1 enforces a maximum parameter limit (resulting in HTTP 400
    'too many SQL variables' if exceeded). This test asserts that both the snapshot
    statement and all chunked observation statements adhere to <= 90 parameters.
    """
    scenario = load_scenario_from_file("scenarios/baseline_2026.json")
    model = WW3RiskModel()
    snap_data = create_snapshot(scenario, model=model)

    from scripts.push_snapshot import build_sql_statements

    (snap_sql, snap_params), obs_statements = build_sql_statements(snap_data)

    max_params_limit = 90
    assert len(snap_params) <= max_params_limit, (
        f"snap_params count {len(snap_params)} exceeds {max_params_limit}"
    )

    assert len(obs_statements) > 0, "Expected non-empty obs_statements"
    for idx, (sql, params) in enumerate(obs_statements, 1):
        assert len(params) <= max_params_limit, (
            f"Observation statement {idx} has {len(params)} parameters, which exceeds D1 limit of {max_params_limit}"
        )

