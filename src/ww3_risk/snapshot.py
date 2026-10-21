"""WW3 Risk Model Snapshot Creation and Export for Cloudflare D1 Storage."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .indicators import ScenarioData
from .model import WW3RiskModel


def parse_stale_days(stale_after: str | int | None) -> int:
    """Parse stale duration string like '365d' or integer days into an integer."""
    if not stale_after:
        return 365
    m = re.match(r"^(\d+)d$", str(stale_after).strip())
    if m:
        return int(m.group(1))
    try:
        return int(stale_after)
    except Exception:
        return 365


def create_snapshot(
    scenario: ScenarioData,
    model: Optional[WW3RiskModel] = None,
    computed_at: Optional[str] = None,
    as_of_date: str = "2026-10-21",
) -> Dict[str, Any]:
    """Generate a complete snapshot dictionary matching Cloudflare D1 schema.

    Contains:
    - 'snapshot': Row dict for `index_snapshots` table
    - 'observations': List of row dicts for `indicator_observations` table (34 total)
    """
    if model is None:
        model = WW3RiskModel()

    result = model.evaluate(scenario)

    if not computed_at:
        computed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    clean_ts = re.sub(r"[^0-9a-zA-Z]", "", computed_at)
    snapshot_id = f"snapshot_{scenario.id}_{clean_ts}"

    snapshot_row = {
        "id": snapshot_id,
        "computed_at": computed_at,
        "model_version": __version__,
        "scenario_id": scenario.id,
        "total_index": round(result.global_risk_index, 2),
        "stage": result.stage.stage_number,
        "base_score": round(result.base_structural_score, 2),
        "interaction_bonus": round(result.interactions["total"], 2),
        "gate_multiplier": round(result.gate_factor, 3),
        "peace_capacity": round(result.peace_capacity, 2),
        "band_1y": round(result.probability_bands["1y"].central_pct, 2),
        "band_5y": round(result.probability_bands["5y"].central_pct, 2),
        "band_10y": round(result.probability_bands["10y"].central_pct, 2),
        "layers_json": json.dumps(
            {k: round(v, 2) for k, v in result.layer_scores.items()},
            ensure_ascii=False,
        ),
        "drivers_json": json.dumps(result.top_risk_drivers, ensure_ascii=False),
    }

    observations: List[Dict[str, Any]] = []

    # 1. Five structural layers
    expected_layers = ["L1", "L2", "L3", "L4", "L5"]
    for lid in expected_layers:
        if lid in scenario.layers:
            for ind in scenario.layers[lid].indicators:
                status = ind.get_quality_status(as_of_date=as_of_date)
                is_stale = 1 if status == "stale" else 0
                stale_days = parse_stale_days(ind.stale_after)
                raw_v = str(ind.raw_value) if ind.raw_value is not None else None
                norm_score = ind.normalized_score if ind.normalized_score is not None else ind.value

                observations.append(
                    {
                        "snapshot_id": snapshot_id,
                        "indicator_id": ind.id,
                        "layer": lid,
                        "raw_value": raw_v,
                        "raw_unit": ind.raw_unit or "",
                        "normalized_score": round(float(norm_score), 2),
                        "evidence_level": ind.evidence_level,
                        "source_name": ind.source_name or ind.source or "",
                        "source_url": ind.source_url or "",
                        "observation_date": str(ind.observation_date or ""),
                        "publication_date": str(ind.publication_date or ""),
                        "last_checked": str(ind.last_checked or as_of_date),
                        "stale_after_days": stale_days,
                        "is_stale": is_stale,
                    }
                )

    # 2. Gate buffers
    for buf in scenario.gate_buffers:
        status = buf.get_quality_status(as_of_date=as_of_date)
        is_stale = 1 if status == "stale" else 0
        stale_days = parse_stale_days(buf.stale_after)
        raw_v = str(buf.raw_value) if buf.raw_value is not None else None
        norm_score = buf.normalized_score if buf.normalized_score is not None else buf.value

        observations.append(
            {
                "snapshot_id": snapshot_id,
                "indicator_id": buf.id,
                "layer": "Gate",
                "raw_value": raw_v,
                "raw_unit": buf.raw_unit or "",
                "normalized_score": round(float(norm_score), 2),
                "evidence_level": buf.evidence_level,
                "source_name": buf.source_name or buf.source or "",
                "source_url": buf.source_url or "",
                "observation_date": str(buf.observation_date or ""),
                "publication_date": str(buf.publication_date or ""),
                "last_checked": str(buf.last_checked or as_of_date),
                "stale_after_days": stale_days,
                "is_stale": is_stale,
            }
        )

    return {
        "snapshot": snapshot_row,
        "observations": observations,
    }


def export_snapshot_to_file(
    output_path: str | Path,
    scenario: ScenarioData,
    model: Optional[WW3RiskModel] = None,
    computed_at: Optional[str] = None,
    as_of_date: str = "2026-10-21",
) -> Dict[str, Any]:
    """Export snapshot JSON file ready for D1 upload."""
    data = create_snapshot(
        scenario=scenario,
        model=model,
        computed_at=computed_at,
        as_of_date=as_of_date,
    )
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data
