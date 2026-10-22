"""WW3 Risk Model - Five-layer structural risk index for assessing systemic conflict risk.

Core components:
- Five structural layers (L1: Resources, L2: Distribution, L3: Labor/AI, L4: Power/Security, L5: Fear of Future)
- Peace mechanism gate (multiplier dampening or magnifying risk)
- Interaction effects (L1xL2, L3xL5, L4xGateFailure)
- Four-stage escalation framework
- Scenario probability bands (1y, 5y, 10y)
"""

__version__ = "0.5.0"

from .indicators import Indicator, LayerData, GateBuffer, ScenarioData, load_scenario_from_file
from .model import WW3RiskModel, RiskResult, StageInfo, ProbabilityBand
from .scenarios import compare_scenarios
from .report import generate_markdown_report
from .snapshot import create_snapshot, export_snapshot_to_file

__all__ = [
    "Indicator",
    "LayerData",
    "GateBuffer",
    "ScenarioData",
    "load_scenario_from_file",
    "WW3RiskModel",
    "RiskResult",
    "StageInfo",
    "ProbabilityBand",
    "compare_scenarios",
    "generate_markdown_report",
    "create_snapshot",
    "export_snapshot_to_file",
]
