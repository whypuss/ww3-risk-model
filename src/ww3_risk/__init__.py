"""WW3 Risk Model - Five-layer structural risk index for assessing systemic conflict risk.

Core components:
- Five structural layers (L1: Resources, L2: Distribution, L3: Labor/AI, L4: Power/Security, L5: Fear of Future)
- Peace mechanism gate (multiplier dampening or magnifying risk)
- Interaction effects (L1xL2, L3xL5, L4xGateFailure)
- Four-stage escalation framework
- Scenario probability bands (1y, 5y, 10y)
"""

from .indicators import Indicator, LayerData, GateBuffer, ScenarioData, load_scenario_from_file
from .model import WW3RiskModel, RiskResult, StageInfo, ProbabilityBand
from .scenarios import compare_scenarios
from .report import generate_markdown_report

__version__ = "0.1.0"
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
]
