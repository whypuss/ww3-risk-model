"""Scenario management, shock application, and multi-scenario comparison."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from .indicators import ScenarioData
from .model import RiskResult, WW3RiskModel


def apply_shocks(
    base_scenario: ScenarioData,
    indicator_overrides: Optional[Dict[str, float]] = None,
    buffer_overrides: Optional[Dict[str, float]] = None,
    scenario_id: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> ScenarioData:
    """Create a new scenario by applying delta or explicit overrides to indicators and buffers."""
    scenario_copy = copy.deepcopy(base_scenario)
    if scenario_id:
        scenario_copy.id = scenario_id
    if title:
        scenario_copy.title = title
    if description:
        scenario_copy.description = description

    if indicator_overrides:
        for ind_id, new_val in indicator_overrides.items():
            found = False
            for layer in scenario_copy.layers.values():
                for ind in layer.indicators:
                    if ind.id == ind_id:
                        ind.value = max(0.0, min(100.0, float(new_val)))
                        found = True
                        break
                if found:
                    break

    if buffer_overrides:
        for buf_id, new_val in buffer_overrides.items():
            for buf in scenario_copy.gate_buffers:
                if buf.id == buf_id:
                    buf.value = max(0.0, min(100.0, float(new_val)))
                    break

    return scenario_copy


def compare_scenarios(
    scenarios: List[ScenarioData],
    model: Optional[WW3RiskModel] = None,
) -> List[RiskResult]:
    """Run model on multiple scenarios and return list of RiskResult."""
    if model is None:
        model = WW3RiskModel()
    return [model.evaluate(s) for s in scenarios]


def format_comparison_ascii_table(results: List[RiskResult]) -> str:
    """Format multiple scenario evaluation results into a clean ASCII comparison table."""
    headers = [
        "Scenario ID",
        "Title",
        "Year",
        "Risk Index",
        "Stage",
        "L1 (Res)",
        "L2 (Dist)",
        "L3 (Work)",
        "L4 (Sec)",
        "L5 (Fear)",
        "Gate Mult",
        "Peace Cap",
        "1y Band",
        "5y Band",
        "10y Band",
    ]

    rows = []
    for r in results:
        rows.append([
            r.scenario_id,
            r.scenario_title[:20],
            str(r.scenario_year),
            f"{r.global_risk_index:.1f}",
            f"Stage {r.stage.stage_number}",
            f"{r.layer_scores.get('L1', 0):.1f}",
            f"{r.layer_scores.get('L2', 0):.1f}",
            f"{r.layer_scores.get('L3', 0):.1f}",
            f"{r.layer_scores.get('L4', 0):.1f}",
            f"{r.layer_scores.get('L5', 0):.1f}",
            f"x{r.gate_factor:.2f}",
            f"{r.peace_capacity:.1f}",
            f"{r.probability_bands['1y'].central_pct:.1f}%",
            f"{r.probability_bands['5y'].central_pct:.1f}%",
            f"{r.probability_bands['10y'].central_pct:.1f}%",
        ])

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    def make_row(values: List[str]) -> str:
        return " | ".join(v.ljust(col_widths[i]) for i, v in enumerate(values))

    sep = "-+-".join("-" * w for w in col_widths)
    header_str = make_row(headers)
    table_lines = [header_str, sep]
    for row in rows:
        table_lines.append(make_row(row))

    return "\n".join(table_lines)
