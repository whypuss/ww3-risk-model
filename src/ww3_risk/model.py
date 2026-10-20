"""Core WW3 Risk Model engine.

Calculates:
- Five structural layer scores (L1..L5)
- Interaction effects (L1xL2, L3xL5, L4xGateFailure)
- Peace mechanism gate multiplier
- Global WW3 Risk Index (0 - 100)
- Stage mapping (Stage 1 to 4)
- Scenario probability bands (1-year, 5-year, 10-year)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .indicators import ScenarioData


@dataclass
class StageInfo:
    """Stage metadata according to the four-stage framework."""
    stage_number: int  # 1 to 4
    code: str  # e.g. "STAGE_1", "STAGE_2", "STAGE_3", "STAGE_4"
    title: str  # Traditional Chinese
    title_en: str
    description: str


@dataclass
class ProbabilityBand:
    """Scenario probability band for a given time horizon."""
    horizon_years: int
    central_pct: float
    lower_pct: float
    upper_pct: float
    disclaimer: str = (
        "結構風險之情境推演估算，非已驗證統計預測；大國全面戰爭歷史基率極低，"
        "結構指數係易燃度而非事件機率（Scenario Estimate, not verified statistical forecast）"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "horizon_years": self.horizon_years,
            "central_pct": round(self.central_pct, 1),
            "lower_pct": round(self.lower_pct, 1),
            "upper_pct": round(self.upper_pct, 1),
            "band_str": f"{round(self.lower_pct, 1)}% – {round(self.upper_pct, 1)}% (中位: {round(self.central_pct, 1)}%)",
            "disclaimer": self.disclaimer,
        }


@dataclass
class RiskResult:
    """Comprehensive evaluation result for a scenario."""
    scenario_id: str
    scenario_title: str
    scenario_year: str | int
    global_risk_index: float  # 0.0 - 100.0
    base_structural_score: float  # Weighted average of 5 layers before interactions & gate
    layer_scores: Dict[str, float]
    layer_weights: Dict[str, float]
    peace_capacity: float  # 0 - 100 (higher = stronger peace mechanisms)
    gate_failure: float  # 0 - 100 (100 - peace_capacity)
    gate_factor: float  # Multiplier applied to structural risk (e.g. 0.6 - 1.4)
    raw_interacted_score: float  # base_structural_score + interaction_total
    interactions: Dict[str, float]  # L1_L2, L3_L5, L4_Gate, total
    stage: StageInfo
    probability_bands: Dict[str, ProbabilityBand]
    top_risk_drivers: List[Dict[str, Any]]
    top_peace_buffers: List[Dict[str, Any]]
    evidence_counts: Dict[str, int]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_title": self.scenario_title,
            "scenario_year": self.scenario_year,
            "global_risk_index": round(self.global_risk_index, 2),
            "base_structural_score": round(self.base_structural_score, 2),
            "raw_interacted_score": round(self.raw_interacted_score, 2),
            "layer_scores": {k: round(v, 2) for k, v in self.layer_scores.items()},
            "layer_weights": self.layer_weights,
            "peace_capacity": round(self.peace_capacity, 2),
            "gate_failure": round(self.gate_failure, 2),
            "gate_factor": round(self.gate_factor, 3),
            "interactions": {k: round(v, 2) for k, v in self.interactions.items()},
            "stage": {
                "number": self.stage.stage_number,
                "code": self.stage.code,
                "title": self.stage.title,
                "title_en": self.stage.title_en,
                "description": self.stage.description,
            },
            "probability_bands": {k: v.to_dict() for k, v in self.probability_bands.items()},
            "top_risk_drivers": self.top_risk_drivers,
            "top_peace_buffers": self.top_peace_buffers,
            "evidence_counts": self.evidence_counts,
            "notes": self.notes,
        }


class WW3RiskModel:
    """Evaluates systemic conflict risk under the 5-layer + gate + interaction framework."""

    # Default Interaction coefficients
    DEFAULT_C_L1_L2 = 0.08  # L1 (Resources) x L2 (Distribution)
    DEFAULT_C_L3_L5 = 0.08  # L3 (Labor/AI) x L5 (Fear of Future)
    DEFAULT_C_L4_GATE = 0.10  # L4 (Power Dilemma) x Gate Failure
    DEFAULT_MAX_INTERACTION_CAP = 25.0  # Max total interaction points

    # Default Gate Multiplier range
    DEFAULT_GATE_MIN = 0.6  # Optimal peace buffers suppress risk up to -40%
    DEFAULT_GATE_MAX = 1.4  # Complete failure of peace buffers amplifies risk up to +40%

    def __init__(
        self,
        c_l1_l2: float = DEFAULT_C_L1_L2,
        c_l3_l5: float = DEFAULT_C_L3_L5,
        c_l4_gate: float = DEFAULT_C_L4_GATE,
        max_interaction_cap: float = DEFAULT_MAX_INTERACTION_CAP,
        gate_min: float = DEFAULT_GATE_MIN,
        gate_max: float = DEFAULT_GATE_MAX,
    ) -> None:
        self.c_l1_l2 = c_l1_l2
        self.c_l3_l5 = c_l3_l5
        self.c_l4_gate = c_l4_gate
        self.max_interaction_cap = max_interaction_cap
        self.gate_min = gate_min
        self.gate_max = gate_max

    def calculate_gate_factor(self, peace_capacity: float) -> float:
        """Calculate gate multiplier M_G in [gate_min, gate_max].

        When peace_capacity = 100: M_G = gate_min (0.6)
        When peace_capacity = 50:  M_G = (gate_min + gate_max) / 2 (1.0)
        When peace_capacity = 0:   M_G = gate_max (1.4)
        """
        p_norm = max(0.0, min(100.0, peace_capacity)) / 100.0
        # Linear interpolation from gate_max down to gate_min as peace increases
        factor = self.gate_max - p_norm * (self.gate_max - self.gate_min)
        return factor

    def calculate_interactions(
        self,
        l1: float,
        l2: float,
        l3: float,
        l4: float,
        l5: float,
        gate_failure: float,
    ) -> Dict[str, float]:
        """Compute the 3 required interaction terms with upper cap."""
        # L1 x L2: Resource shortage meeting inequality amplifies systemic risk
        i_l1_l2 = self.c_l1_l2 * (l1 * l2 / 100.0)

        # L3 x L5: Labor/AI displacement despair meeting future pessimism
        i_l3_l5 = self.c_l3_l5 * (l3 * l5 / 100.0)

        # L4 x Gate Failure: Security dilemma meeting collapsed peace mechanisms
        i_l4_gate = self.c_l4_gate * (l4 * gate_failure / 100.0)

        sum_raw = i_l1_l2 + i_l3_l5 + i_l4_gate
        total_capped = min(self.max_interaction_cap, sum_raw)

        return {
            "L1_x_L2": round(i_l1_l2, 3),
            "L3_x_L5": round(i_l3_l5, 3),
            "L4_x_GateFailure": round(i_l4_gate, 3),
            "raw_sum": round(sum_raw, 3),
            "total": round(total_capped, 3),
            "is_capped": sum_raw > self.max_interaction_cap,
        }

    @staticmethod
    def soft_clamp(x: float, threshold: float = 70.0, ceiling: float = 100.0) -> float:
        """Smoothly compresses extreme values above threshold towards ceiling (100.0).

        Ensures:
        - Exact identity f(x) = x for normal/moderate range (x <= threshold)
        - Strictly monotonic increasing C^1 smooth curve for extreme range (x > threshold)
        - Distinct scores even for near-maximum historical and shock scenarios (avoids flat clamping)
        """
        if x <= 0.0:
            return 0.0
        if x <= threshold:
            return x
        # Scale remaining interval with hyperbolic tangent
        span = ceiling - threshold
        return threshold + span * math.tanh((x - threshold) / span)

    @staticmethod
    def map_stage(score: float) -> StageInfo:
        """Map global risk score (0-100) to four-stage escalation framework."""
        if score < 25.0:
            return StageInfo(
                stage_number=1,
                code="STAGE_1_PRESSURE_BUILDING",
                title="階段一：結構壓力形成",
                title_en="Stage 1: Structural Pressure Building",
                description="資源、分配或經濟摩擦處於低位累積期，體系彈性充裕，國際制度能有效吸收爭端。",
            )
        elif score < 50.0:
            return StageInfo(
                stage_number=2,
                code="STAGE_2_CONFLICT_OF_INTERESTS",
                title="階段二：利益衝突顯性化",
                title_en="Stage 2: Overt Conflict of Interests",
                description="關鍵產業、地緣勢力範圍或未來預期出現顯著分歧，陣營對立升溫，但常規外交與經貿制衡依然有效。",
            )
        elif score < 85.0:
            return StageInfo(
                stage_number=3,
                code="STAGE_3_PEACE_MECHANISM_FAILURE",
                title="階段三：和平解決機制失效",
                title_en="Stage 3: Breakdown of Peace Mechanisms",
                description="外交互信受挫、貿易脫鉤武器化，多邊仲裁癱瘓，安全困境進入自我強化之高危狀態。",
            )
        else:
            return StageInfo(
                stage_number=4,
                code="STAGE_4_VIOLENCE_ACCEPTED",
                title="階段四：暴力成為被接受選項",
                title_en="Stage 4: Violence Accepted as Viable Option",
                description="和平緩衝全面失靈，生存危機、預防性打擊邏輯或體系絕望感壓倒避戰共識，爆發總體戰衝突機率極高。",
            )

    @staticmethod
    def calculate_probability_bands(score: float) -> Dict[str, ProbabilityBand]:
        """Estimate 1-year, 5-year, and 10-year scenario probability bands via calibrated conservative mapping.

        Calibrated against empirical anchor table (tolerance +-3%, 100 +-5%):
        - Index 25:  1y ~0.5% (0.4%),  5y ~2.0% (1.6%),  10y ~5.0% (3.2%)
        - Index 50:  1y ~2.0% (1.7%),  5y ~8.0% (6.5%),  10y ~15.0% (12.6%)
        - Index 75:  1y ~6.0% (6.2%),  5y ~22.0% (22.7%), 10y ~38.0% (38.3%)
        - Index 85:  1y ~10.0% (10.2%), 5y ~32.0% (34.1%), 10y ~50.0% (52.6%)
        - Index 100: 1y ~20.0% (20.0%), 5y ~55.0% (54.3%), 10y ~75.0% (72.3%)

        Properties:
        - Smooth, strictly monotonic increasing C^inf logistic curves
        - Strictly 1y < 5y < 10y for all s in [0, 100]
        - Asymptotically avoids 0% or 100%
        """
        s = max(0.0, min(100.0, score))

        # Parameters calibrated for conservative systemic war risk horizon:
        # 1-Year: Acute flashpoint trigger window
        # 5-Year: Structural crisis accumulation window
        # 10-Year: Hegemonic transition & long-wave confrontation window
        horizons = [
            # (years, L_max, k, x0, lower_ratio, upper_ratio)
            (1, 80.0, 0.055, 120.0, 0.65, 1.45),
            (5, 95.0, 0.058, 95.0, 0.75, 1.30),
            (10, 98.0, 0.059, 82.5, 0.80, 1.25),
        ]

        bands: Dict[str, ProbabilityBand] = {}
        for years, l_max, k, x0, low_r, up_r in horizons:
            central = l_max / (1.0 + math.exp(-k * (s - x0)))
            lower = max(0.1, central * low_r)
            upper = min(100.0, central * up_r)
            bands[f"{years}y"] = ProbabilityBand(
                horizon_years=years,
                central_pct=central,
                lower_pct=lower,
                upper_pct=upper,
            )

        return bands

    def evaluate(self, scenario: ScenarioData) -> RiskResult:
        """Run full evaluation on ScenarioData."""
        # 1. Five Layer Scores
        expected_layers = ["L1", "L2", "L3", "L4", "L5"]
        layer_scores: Dict[str, float] = {}
        layer_weights: Dict[str, float] = {}

        for lid in expected_layers:
            if lid in scenario.layers:
                layer_scores[lid] = scenario.layers[lid].calculate_score()
                layer_weights[lid] = scenario.layers[lid].weight
            else:
                layer_scores[lid] = 0.0
                layer_weights[lid] = 1.0

        total_weight = sum(layer_weights.values())
        if total_weight > 0:
            base_structural = sum(layer_scores[k] * layer_weights[k] for k in expected_layers) / total_weight
        else:
            base_structural = sum(layer_scores.values()) / len(layer_scores)

        # 2. Peace Mechanism Gate
        peace_capacity = scenario.calculate_peace_capacity()
        gate_failure = scenario.calculate_gate_failure()
        gate_factor = self.calculate_gate_factor(peace_capacity)

        # 3. Interactions
        interactions = self.calculate_interactions(
            l1=layer_scores["L1"],
            l2=layer_scores["L2"],
            l3=layer_scores["L3"],
            l4=layer_scores["L4"],
            l5=layer_scores["L5"],
            gate_failure=gate_failure,
        )
        interaction_total = interactions["total"]

        # 4. Gated Structural Score
        # Raw structural risk before gating = base_structural + interaction_total
        raw_interacted = base_structural + interaction_total
        gated_score = raw_interacted * gate_factor

        # 5. Soft-clamped Global WW3 Risk Index (avoids premature saturation at high extremes)
        global_risk_index = self.soft_clamp(gated_score, threshold=70.0, ceiling=100.0)

        # 6. Stage & Probability Bands
        stage = self.map_stage(global_risk_index)
        prob_bands = self.calculate_probability_bands(global_risk_index)

        # 7. Identify Top Risk Drivers & Peace Dampeners
        all_indicators: List[Tuple[str, str, str, float, float]] = []
        for lid in expected_layers:
            if lid in scenario.layers:
                for ind in scenario.layers[lid].indicators:
                    all_indicators.append((lid, ind.id, ind.name, ind.value, ind.weight))

        # Sort by value descending
        all_indicators.sort(key=lambda x: x[3], reverse=True)
        top_risk_drivers = [
            {"layer": x[0], "id": x[1], "name": x[2], "value": round(x[3], 2), "weight": x[4]}
            for x in all_indicators[:5]
        ]

        # Peace buffers sorted by capacity descending (most effective buffers)
        active_buffers = [
            {"id": b.id, "name": b.name, "capacity": round(b.value, 2), "weight": b.weight}
            for b in scenario.gate_buffers
        ]
        active_buffers.sort(key=lambda x: x["capacity"], reverse=True)

        notes = [
            f"Base structural score: {round(base_structural, 2)}",
            f"Interaction bonus: +{round(interaction_total, 2)} (cap: {self.max_interaction_cap})",
            f"Peace capacity: {round(peace_capacity, 2)} -> Gate multiplier: x{round(gate_factor, 3)}",
            f"Gated score: {round(gated_score, 2)} -> Index: {round(global_risk_index, 2)}",
        ]

        return RiskResult(
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            scenario_year=scenario.year,
            global_risk_index=global_risk_index,
            base_structural_score=base_structural,
            layer_scores=layer_scores,
            layer_weights=layer_weights,
            peace_capacity=peace_capacity,
            gate_failure=gate_failure,
            gate_factor=gate_factor,
            raw_interacted_score=raw_interacted,
            interactions=interactions,
            stage=stage,
            probability_bands=prob_bands,
            top_risk_drivers=top_risk_drivers,
            top_peace_buffers=active_buffers,
            evidence_counts=scenario.count_evidence_levels(),
            notes=notes,
        )
