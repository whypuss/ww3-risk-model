#!/usr/bin/env python3
"""Push a WW3 Risk Model snapshot JSON to Cloudflare D1 Database via REST API.

Environment variables required:
- CLOUDFLARE_ACCOUNT_ID
- CLOUDFLARE_D1_DATABASE_ID
- CLOUDFLARE_API_TOKEN
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def get_env_credentials() -> Tuple[str, str, str]:
    """Retrieve and validate Cloudflare credentials from environment variables."""
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    database_id = os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()

    missing = []
    if not account_id:
        missing.append("CLOUDFLARE_ACCOUNT_ID")
    if not database_id:
        missing.append("CLOUDFLARE_D1_DATABASE_ID")
    if not api_token:
        missing.append("CLOUDFLARE_API_TOKEN")

    if missing:
        raise ValueError(
            f"Missing required Cloudflare environment variables: {', '.join(missing)}\n"
            f"Please set these variables before pushing snapshot to D1."
        )

    return account_id, database_id, api_token


def execute_d1_query(
    account_id: str,
    database_id: str,
    api_token: str,
    sql: str,
    params: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Execute a single parameterized SQL query against Cloudflare D1 HTTP API."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
    payload: Dict[str, Any] = {"sql": sql}
    if params:
        payload["params"] = params

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "ww3-risk-d1-pusher/0.4.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_bytes = resp.read()
            resp_json = json.loads(resp_bytes.decode("utf-8"))
            if not resp_json.get("success"):
                errors = resp_json.get("errors", [])
                raise RuntimeError(f"Cloudflare D1 API query returned unsuccessful: {errors}")
            return resp_json
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP Error {e.code} querying D1 API: {err_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error connecting to D1 API: {e.reason}") from e


def build_sql_statements(snapshot_data: Dict[str, Any]) -> Tuple[Tuple[str, List[Any]], List[Tuple[str, List[Any]]]]:
    """Build parameterized SQL statements for index_snapshots and indicator_observations."""
    snap = snapshot_data.get("snapshot")
    if not snap:
        raise ValueError("Invalid snapshot data: missing 'snapshot' object.")
    obs_list = snapshot_data.get("observations", [])

    snap_sql = (
        "INSERT INTO index_snapshots ("
        "id, computed_at, model_version, scenario_id, total_index, stage, "
        "base_score, interaction_bonus, gate_multiplier, peace_capacity, "
        "band_1y, band_5y, band_10y, layers_json, drivers_json"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    snap_params = [
        snap["id"],
        snap["computed_at"],
        snap["model_version"],
        snap["scenario_id"],
        float(snap["total_index"]),
        int(snap["stage"]),
        float(snap["base_score"]),
        float(snap["interaction_bonus"]),
        float(snap["gate_multiplier"]),
        float(snap["peace_capacity"]),
        float(snap["band_1y"]),
        float(snap["band_5y"]),
        float(snap["band_10y"]),
        snap["layers_json"] if isinstance(snap["layers_json"], str) else json.dumps(snap["layers_json"], ensure_ascii=False),
        snap["drivers_json"] if isinstance(snap["drivers_json"], str) else json.dumps(snap["drivers_json"], ensure_ascii=False),
    ]

    obs_statements: List[Tuple[str, List[Any]]] = []
    # Batch observations in chunks of 10 to stay well within SQL parameter limits
    chunk_size = 10
    cols = (
        "snapshot_id, indicator_id, layer, raw_value, raw_unit, "
        "normalized_score, evidence_level, source_name, source_url, "
        "observation_date, publication_date, last_checked, stale_after_days, is_stale"
    )

    for i in range(0, len(obs_list), chunk_size):
        chunk = obs_list[i : i + chunk_size]
        placeholders = ", ".join(["(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"] * len(chunk))
        chunk_sql = f"INSERT INTO indicator_observations ({cols}) VALUES {placeholders}"
        chunk_params: List[Any] = []
        for o in chunk:
            raw_v = str(o["raw_value"]) if o.get("raw_value") is not None else None
            chunk_params.extend([
                o["snapshot_id"],
                o["indicator_id"],
                o["layer"],
                raw_v,
                o.get("raw_unit", ""),
                float(o["normalized_score"]),
                o.get("evidence_level", "illustrative"),
                o.get("source_name", ""),
                o.get("source_url", ""),
                str(o.get("observation_date", "")),
                str(o.get("publication_date", "")),
                str(o.get("last_checked", "")),
                int(o.get("stale_after_days", 365)),
                int(o.get("is_stale", 0)),
            ])
        obs_statements.append((chunk_sql, chunk_params))

    return (snap_sql, snap_params), obs_statements


def push_to_sqlite(db_path: str | Path, snapshot_data: Dict[str, Any]) -> None:
    """Execute parameterized SQL insertion into a local SQLite database (for testing/verification)."""
    (snap_sql, snap_params), obs_statements = build_sql_statements(snapshot_data)
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(snap_sql, snap_params)
            for obs_sql, obs_params in obs_statements:
                conn.execute(obs_sql, obs_params)
    finally:
        conn.close()


def push_snapshot(
    snapshot_data: Dict[str, Any],
    account_id: Optional[str] = None,
    database_id: Optional[str] = None,
    api_token: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """Validate and push snapshot data to Cloudflare D1."""
    (snap_sql, snap_params), obs_statements = build_sql_statements(snapshot_data)
    snap = snapshot_data["snapshot"]
    obs_count = len(snapshot_data.get("observations", []))

    if dry_run:
        print("[DRY-RUN] Snapshot validation successful:")
        print(f"  Snapshot ID   : {snap['id']}")
        print(f"  Computed At   : {snap['computed_at']}")
        print(f"  Total Index   : {snap['total_index']} (Stage {snap['stage']})")
        print(f"  Observations  : {obs_count} rows across {len(obs_statements)} batch SQL queries")
        print(f"  Param count   : {len(snap_params)} (snapshot), {sum(len(p) for _, p in obs_statements)} (observations)")
        print("[DRY-RUN] No remote API calls made.")
        return

    if not account_id or not database_id or not api_token:
        account_id, database_id, api_token = get_env_credentials()

    print(f"Pushing snapshot {snap['id']} to Cloudflare D1 ({database_id})...")

    # 1. Insert snapshot record
    res_snap = execute_d1_query(account_id, database_id, api_token, snap_sql, snap_params)
    print("  ✓ index_snapshots record inserted")

    # 2. Insert observations in batches
    for idx, (obs_sql, obs_params) in enumerate(obs_statements, 1):
        execute_d1_query(account_id, database_id, api_token, obs_sql, obs_params)
        print(f"  ✓ indicator_observations batch {idx}/{len(obs_statements)} inserted")

    print(f"Successfully pushed snapshot {snap['id']} ({obs_count} observations) to D1.")


def main(args: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Push WW3 Risk Model snapshot to Cloudflare D1")
    parser.add_argument("snapshot_file", type=str, help="Path to snapshot JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview SQL without calling D1 API")
    parser.add_argument("--sqlite", type=str, help="Insert into local SQLite DB instead of Cloudflare D1")

    parsed = parser.parse_args(args)

    snapshot_path = Path(parsed.snapshot_file)
    if not snapshot_path.exists():
        print(f"Error: Snapshot file not found: {snapshot_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot_data = json.load(f)
    except Exception as e:
        print(f"Error reading snapshot JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if parsed.sqlite:
        try:
            push_to_sqlite(parsed.sqlite, snapshot_data)
            print(f"Successfully inserted snapshot into local SQLite: {parsed.sqlite}")
            sys.exit(0)
        except Exception as e:
            print(f"Error writing to SQLite: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        push_snapshot(snapshot_data=snapshot_data, dry_run=parsed.dry_run)
    except ValueError as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Execution Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
