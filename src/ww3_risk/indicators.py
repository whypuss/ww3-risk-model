"""Indicator definitions, validation, and serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


VALID_EVIDENCE_LEVELS = {"verified", "inference", "illustrative"}


@dataclass
class Indicator:
    """Single indicator within a layer."""
    id: str
    name: str
    name_en: str
    value: float  # Raw risk value 0.0 - 100.0 (higher = higher structural risk)
    weight: float = 1.0  # Relative weight within layer
    evidence_level: str = "illustrative"  # verified | inference | illustrative
    source: str = ""
    source_url: str = ""
    year: str | int = 2026
    note: str = ""
    retrieval_note: str = ""

    def __post_init__(self) -> None:
        self.value = float(self.value)
        self.weight = float(self.weight)
        if not (0.0 <= self.value <= 100.0):
            raise ValueError(f"Indicator '{self.id}' value must be between 0 and 100, got {self.value}")
        if self.weight <= 0:
            raise ValueError(f"Indicator '{self.id}' weight must be positive, got {self.weight}")
        if self.evidence_level not in VALID_EVIDENCE_LEVELS:
            raise ValueError(
                f"Indicator '{self.id}' evidence_level must be one of {VALID_EVIDENCE_LEVELS}, got '{self.evidence_level}'"
            )

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "name": self.name,
            "name_en": self.name_en,
            "value": round(self.value, 2),
            "weight": self.weight,
            "evidence_level": self.evidence_level,
            "source": self.source,
            "year": self.year,
            "note": self.note,
        }
        if self.source_url:
            d["source_url"] = self.source_url
        if self.retrieval_note:
            d["retrieval_note"] = self.retrieval_note
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Indicator:
        return cls(
            id=data["id"],
            name=data["name"],
            name_en=data.get("name_en", data["id"]),
            value=float(data["value"]),
            weight=float(data.get("weight", 1.0)),
            evidence_level=data.get("evidence_level", "illustrative"),
            source=data.get("source", ""),
            source_url=data.get("source_url", ""),
            year=data.get("year", 2026),
            note=data.get("note", ""),
            retrieval_note=data.get("retrieval_note", ""),
        )


@dataclass
class LayerData:
    """A layer containing multiple indicators and an overall layer weight."""
    id: str  # e.g., 'L1', 'L2', 'L3', 'L4', 'L5'
    name: str
    name_en: str
    weight: float = 1.0  # Weight in base structural risk calculation
    indicators: List[Indicator] = field(default_factory=list)

    def calculate_score(self) -> float:
        """Calculate weighted score for the layer (0.0 - 100.0)."""
        if not self.indicators:
            return 0.0
        total_weight = sum(ind.weight for ind in self.indicators)
        if total_weight <= 0:
            return 0.0
        raw_score = sum(ind.value * ind.weight for ind in self.indicators) / total_weight
        return max(0.0, min(100.0, raw_score))

    def get_indicator(self, ind_id: str) -> Optional[Indicator]:
        for ind in self.indicators:
            if ind.id == ind_id:
                return ind
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "name_en": self.name_en,
            "weight": self.weight,
            "indicators": [ind.to_dict() for ind in self.indicators],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LayerData:
        indicators = [Indicator.from_dict(ind) for ind in data.get("indicators", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            name_en=data.get("name_en", data["id"]),
            weight=float(data.get("weight", 1.0)),
            indicators=indicators,
        )


@dataclass
class GateBuffer:
    """A peace mechanism buffer indicator (higher value = stronger peace dampener)."""
    id: str
    name: str
    name_en: str
    value: float  # Capacity 0.0 - 100.0 (100 = optimal peace mechanism, 0 = total collapse)
    weight: float = 1.0
    evidence_level: str = "illustrative"
    source: str = ""
    source_url: str = ""
    year: str | int = 2026
    note: str = ""
    retrieval_note: str = ""

    def __post_init__(self) -> None:
        self.value = float(self.value)
        self.weight = float(self.weight)
        if not (0.0 <= self.value <= 100.0):
            raise ValueError(f"Gate buffer '{self.id}' value must be between 0 and 100, got {self.value}")
        if self.weight <= 0:
            raise ValueError(f"Gate buffer '{self.id}' weight must be positive, got {self.weight}")
        if self.evidence_level not in VALID_EVIDENCE_LEVELS:
            raise ValueError(
                f"Gate buffer '{self.id}' evidence_level must be one of {VALID_EVIDENCE_LEVELS}, got '{self.evidence_level}'"
            )

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "name": self.name,
            "name_en": self.name_en,
            "value": round(self.value, 2),
            "weight": self.weight,
            "evidence_level": self.evidence_level,
            "source": self.source,
            "year": self.year,
            "note": self.note,
        }
        if self.source_url:
            d["source_url"] = self.source_url
        if self.retrieval_note:
            d["retrieval_note"] = self.retrieval_note
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GateBuffer:
        return cls(
            id=data["id"],
            name=data["name"],
            name_en=data.get("name_en", data["id"]),
            value=float(data["value"]),
            weight=float(data.get("weight", 1.0)),
            evidence_level=data.get("evidence_level", "illustrative"),
            source=data.get("source", ""),
            source_url=data.get("source_url", ""),
            year=data.get("year", 2026),
            note=data.get("note", ""),
            retrieval_note=data.get("retrieval_note", ""),
        )


@dataclass
class ScenarioData:
    """Full scenario data including 5 layers and peace mechanism gate buffers."""
    id: str
    title: str
    title_en: str
    description: str
    year: str | int = 2026
    layers: Dict[str, LayerData] = field(default_factory=dict)
    gate_buffers: List[GateBuffer] = field(default_factory=list)

    def get_layer_score(self, layer_id: str) -> float:
        if layer_id in self.layers:
            return self.layers[layer_id].calculate_score()
        return 0.0

    def calculate_peace_capacity(self) -> float:
        """Overall peace mechanism capacity score (0.0 to 100.0)."""
        if not self.gate_buffers:
            return 50.0  # Neutral default
        total_w = sum(buf.weight for buf in self.gate_buffers)
        if total_w <= 0:
            return 50.0
        raw = sum(buf.value * buf.weight for buf in self.gate_buffers) / total_w
        return max(0.0, min(100.0, raw))

    def calculate_gate_failure(self) -> float:
        """Gate failure score (0 = functioning, 100 = completely failed)."""
        return 100.0 - self.calculate_peace_capacity()

    def count_evidence_levels(self) -> Dict[str, int]:
        counts = {"verified": 0, "inference": 0, "illustrative": 0}
        for layer in self.layers.values():
            for ind in layer.indicators:
                counts[ind.evidence_level] = counts.get(ind.evidence_level, 0) + 1
        for buf in self.gate_buffers:
            counts[buf.evidence_level] = counts.get(buf.evidence_level, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "title_en": self.title_en,
            "description": self.description,
            "year": self.year,
            "layers": {lid: layer.to_dict() for lid, layer in self.layers.items()},
            "gate_buffers": [b.to_dict() for b in self.gate_buffers],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScenarioData:
        layers: Dict[str, LayerData] = {}
        for lid, ldata in data.get("layers", {}).items():
            layers[lid] = LayerData.from_dict(ldata)

        gate_buffers = [GateBuffer.from_dict(b) for b in data.get("gate_buffers", [])]
        return cls(
            id=data["id"],
            title=data.get("title", data["id"]),
            title_en=data.get("title_en", data["id"]),
            description=data.get("description", ""),
            year=data.get("year", 2026),
            layers=layers,
            gate_buffers=gate_buffers,
        )


def load_scenario_from_file(file_path: str | Path) -> ScenarioData:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ScenarioData.from_dict(data)
