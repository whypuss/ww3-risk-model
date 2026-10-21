"""Indicator definitions, validation, and serialization with v0.3 data quality tracking."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


VALID_EVIDENCE_LEVELS = {"verified", "inference", "illustrative"}
VALID_QUALITY_STATUSES = {"fresh", "stale", "missing"}


@dataclass
class Indicator:
    """Single indicator within a layer, supporting rich v0.3 provenance and quality metadata."""
    id: str
    name: str
    name_en: str
    value: float  # Normalized risk value 0.0 - 100.0 (higher = higher structural risk)
    weight: float = 1.0  # Relative weight within layer
    evidence_level: str = "illustrative"  # verified | inference | illustrative
    source: str = ""
    source_name: str = ""
    source_url: str = ""
    year: str | int = 2026
    observation_date: str = ""
    publication_date: str = ""
    last_checked: str = "2026-10-21"
    update_frequency: str = "annual"  # annual | semi-annual | quarterly | monthly | biennial | triennial
    stale_after: str = "365d"  # e.g., '365d', '730d', '180d'
    raw_value: Any = None
    raw_unit: str = ""
    normalized_score: Optional[float] = None
    normalization_method: str = ""
    scoring_rubric: str = ""
    applicability_note: str = ""
    uncertainty_note: str = ""
    note: str = ""
    retrieval_note: str = ""

    def __post_init__(self) -> None:
        self.value = float(self.value)
        self.weight = float(self.weight)
        if self.normalized_score is None:
            self.normalized_score = self.value
        else:
            self.normalized_score = float(self.normalized_score)

        if not self.source_name and self.source:
            self.source_name = self.source
        if not self.source and self.source_name:
            self.source = self.source_name

        if not self.observation_date:
            self.observation_date = str(self.year)
        if not self.publication_date:
            self.publication_date = str(self.year)

        if not (0.0 <= self.value <= 100.0):
            raise ValueError(f"Indicator '{self.id}' value must be between 0 and 100, got {self.value}")
        if self.weight <= 0:
            raise ValueError(f"Indicator '{self.id}' weight must be positive, got {self.weight}")
        if self.evidence_level not in VALID_EVIDENCE_LEVELS:
            raise ValueError(
                f"Indicator '{self.id}' evidence_level must be one of {VALID_EVIDENCE_LEVELS}, got '{self.evidence_level}'"
            )

    def get_quality_status(self, as_of_date: str = "2026-10-21") -> str:
        """Evaluate indicator quality status: 'fresh' | 'stale' | 'missing'."""
        # 1. Missingness checks
        if self.raw_value is None or str(self.raw_value).strip() == "":
            if self.evidence_level == "illustrative" and not self.scoring_rubric:
                return "missing"
            if self.evidence_level in ("verified", "inference"):
                return "missing"

        effective_source = self.source_name or self.source
        if not effective_source:
            return "missing"

        # 2. Staleness checks
        stale_days = 365
        if self.stale_after:
            m = re.match(r"^(\d+)d$", str(self.stale_after).strip())
            if m:
                stale_days = int(m.group(1))

        ref_date_str = self.publication_date or self.observation_date or str(self.year)
        ref_date = None
        try:
            m_date = re.search(r"(\d{4})-(\d{2})-(\d{2})", ref_date_str)
            if m_date:
                ref_date = datetime(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
            else:
                m_year = re.search(r"(\d{4})", ref_date_str)
                if m_year:
                    ref_date = datetime(int(m_year.group(1)), 1, 1)
        except Exception:
            ref_date = None

        as_of = None
        try:
            m_as_of = re.search(r"(\d{4})-(\d{2})-(\d{2})", as_of_date)
            if m_as_of:
                as_of = datetime(int(m_as_of.group(1)), int(m_as_of.group(2)), int(m_as_of.group(3)))
            else:
                as_of = datetime(2026, 10, 21)
        except Exception:
            as_of = datetime(2026, 10, 21)

        if ref_date and as_of:
            days_diff = (as_of - ref_date).days
            if days_diff > stale_days:
                return "stale"

        return "fresh"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
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
        if self.source_name:
            d["source_name"] = self.source_name
        if self.source_url:
            d["source_url"] = self.source_url
        if self.observation_date:
            d["observation_date"] = self.observation_date
        if self.publication_date:
            d["publication_date"] = self.publication_date
        if self.last_checked:
            d["last_checked"] = self.last_checked
        if self.update_frequency:
            d["update_frequency"] = self.update_frequency
        if self.stale_after:
            d["stale_after"] = self.stale_after
        if self.raw_value is not None:
            d["raw_value"] = self.raw_value
        if self.raw_unit:
            d["raw_unit"] = self.raw_unit
        if self.normalized_score is not None:
            d["normalized_score"] = round(self.normalized_score, 2)
        if self.normalization_method:
            d["normalization_method"] = self.normalization_method
        if self.scoring_rubric:
            d["scoring_rubric"] = self.scoring_rubric
        if self.applicability_note:
            d["applicability_note"] = self.applicability_note
        if self.uncertainty_note:
            d["uncertainty_note"] = self.uncertainty_note
        if self.retrieval_note:
            d["retrieval_note"] = self.retrieval_note
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Indicator:
        return cls(
            id=data["id"],
            name=data["name"],
            name_en=data.get("name_en", data["id"]),
            value=float(data.get("value", data.get("normalized_score", 0.0))),
            weight=float(data.get("weight", 1.0)),
            evidence_level=data.get("evidence_level", "illustrative"),
            source=data.get("source", data.get("source_name", "")),
            source_name=data.get("source_name", data.get("source", "")),
            source_url=data.get("source_url", ""),
            year=data.get("year", 2026),
            observation_date=data.get("observation_date", str(data.get("year", "2026"))),
            publication_date=data.get("publication_date", str(data.get("year", "2026"))),
            last_checked=data.get("last_checked", "2026-10-21"),
            update_frequency=data.get("update_frequency", "annual"),
            stale_after=data.get("stale_after", "365d"),
            raw_value=data.get("raw_value", None),
            raw_unit=data.get("raw_unit", ""),
            normalized_score=float(data["normalized_score"]) if "normalized_score" in data else None,
            normalization_method=data.get("normalization_method", ""),
            scoring_rubric=data.get("scoring_rubric", ""),
            applicability_note=data.get("applicability_note", ""),
            uncertainty_note=data.get("uncertainty_note", ""),
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
    source_name: str = ""
    source_url: str = ""
    year: str | int = 2026
    observation_date: str = ""
    publication_date: str = ""
    last_checked: str = "2026-10-21"
    update_frequency: str = "annual"
    stale_after: str = "365d"
    raw_value: Any = None
    raw_unit: str = ""
    normalized_score: Optional[float] = None
    normalization_method: str = ""
    scoring_rubric: str = ""
    applicability_note: str = ""
    uncertainty_note: str = ""
    note: str = ""
    retrieval_note: str = ""

    def __post_init__(self) -> None:
        self.value = float(self.value)
        self.weight = float(self.weight)
        if self.normalized_score is None:
            self.normalized_score = self.value
        else:
            self.normalized_score = float(self.normalized_score)

        if not self.source_name and self.source:
            self.source_name = self.source
        if not self.source and self.source_name:
            self.source = self.source_name

        if not self.observation_date:
            self.observation_date = str(self.year)
        if not self.publication_date:
            self.publication_date = str(self.year)

        if not (0.0 <= self.value <= 100.0):
            raise ValueError(f"Gate buffer '{self.id}' value must be between 0 and 100, got {self.value}")
        if self.weight <= 0:
            raise ValueError(f"Gate buffer '{self.id}' weight must be positive, got {self.weight}")
        if self.evidence_level not in VALID_EVIDENCE_LEVELS:
            raise ValueError(
                f"Gate buffer '{self.id}' evidence_level must be one of {VALID_EVIDENCE_LEVELS}, got '{self.evidence_level}'"
            )

    def get_quality_status(self, as_of_date: str = "2026-10-21") -> str:
        """Evaluate gate buffer quality status: 'fresh' | 'stale' | 'missing'."""
        if self.raw_value is None or str(self.raw_value).strip() == "":
            if self.evidence_level == "illustrative" and not self.scoring_rubric:
                return "missing"
            if self.evidence_level in ("verified", "inference"):
                return "missing"

        effective_source = self.source_name or self.source
        if not effective_source:
            return "missing"

        stale_days = 365
        if self.stale_after:
            m = re.match(r"^(\d+)d$", str(self.stale_after).strip())
            if m:
                stale_days = int(m.group(1))

        ref_date_str = self.publication_date or self.observation_date or str(self.year)
        ref_date = None
        try:
            m_date = re.search(r"(\d{4})-(\d{2})-(\d{2})", ref_date_str)
            if m_date:
                ref_date = datetime(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
            else:
                m_year = re.search(r"(\d{4})", ref_date_str)
                if m_year:
                    ref_date = datetime(int(m_year.group(1)), 1, 1)
        except Exception:
            ref_date = None

        as_of = None
        try:
            m_as_of = re.search(r"(\d{4})-(\d{2})-(\d{2})", as_of_date)
            if m_as_of:
                as_of = datetime(int(m_as_of.group(1)), int(m_as_of.group(2)), int(m_as_of.group(3)))
            else:
                as_of = datetime(2026, 10, 21)
        except Exception:
            as_of = datetime(2026, 10, 21)

        if ref_date and as_of:
            days_diff = (as_of - ref_date).days
            if days_diff > stale_days:
                return "stale"

        return "fresh"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
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
        if self.source_name:
            d["source_name"] = self.source_name
        if self.source_url:
            d["source_url"] = self.source_url
        if self.observation_date:
            d["observation_date"] = self.observation_date
        if self.publication_date:
            d["publication_date"] = self.publication_date
        if self.last_checked:
            d["last_checked"] = self.last_checked
        if self.update_frequency:
            d["update_frequency"] = self.update_frequency
        if self.stale_after:
            d["stale_after"] = self.stale_after
        if self.raw_value is not None:
            d["raw_value"] = self.raw_value
        if self.raw_unit:
            d["raw_unit"] = self.raw_unit
        if self.normalized_score is not None:
            d["normalized_score"] = round(self.normalized_score, 2)
        if self.normalization_method:
            d["normalization_method"] = self.normalization_method
        if self.scoring_rubric:
            d["scoring_rubric"] = self.scoring_rubric
        if self.applicability_note:
            d["applicability_note"] = self.applicability_note
        if self.uncertainty_note:
            d["uncertainty_note"] = self.uncertainty_note
        if self.retrieval_note:
            d["retrieval_note"] = self.retrieval_note
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GateBuffer:
        return cls(
            id=data["id"],
            name=data["name"],
            name_en=data.get("name_en", data["id"]),
            value=float(data.get("value", data.get("normalized_score", 0.0))),
            weight=float(data.get("weight", 1.0)),
            evidence_level=data.get("evidence_level", "illustrative"),
            source=data.get("source", data.get("source_name", "")),
            source_name=data.get("source_name", data.get("source", "")),
            source_url=data.get("source_url", ""),
            year=data.get("year", 2026),
            observation_date=data.get("observation_date", str(data.get("year", "2026"))),
            publication_date=data.get("publication_date", str(data.get("year", "2026"))),
            last_checked=data.get("last_checked", "2026-10-21"),
            update_frequency=data.get("update_frequency", "annual"),
            stale_after=data.get("stale_after", "365d"),
            raw_value=data.get("raw_value", None),
            raw_unit=data.get("raw_unit", ""),
            normalized_score=float(data["normalized_score"]) if "normalized_score" in data else None,
            normalization_method=data.get("normalization_method", ""),
            scoring_rubric=data.get("scoring_rubric", ""),
            applicability_note=data.get("applicability_note", ""),
            uncertainty_note=data.get("uncertainty_note", ""),
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

    def calculate_data_quality(self, as_of_date: str = "2026-10-21") -> Dict[str, Any]:
        """Compile comprehensive data quality report per P3 specification."""
        items: List[Dict[str, Any]] = []
        fresh_count = 0
        stale_count = 0
        missing_count = 0

        for lid, layer in self.layers.items():
            for ind in layer.indicators:
                status = ind.get_quality_status(as_of_date=as_of_date)
                if status == "fresh":
                    fresh_count += 1
                elif status == "stale":
                    stale_count += 1
                else:
                    missing_count += 1

                items.append({
                    "id": ind.id,
                    "name": ind.name,
                    "layer": lid,
                    "status": status,
                    "evidence_level": ind.evidence_level,
                    "raw_value": ind.raw_value,
                    "raw_unit": ind.raw_unit,
                    "source_name": ind.source_name or ind.source,
                    "source_url": ind.source_url,
                    "publication_date": ind.publication_date,
                    "last_checked": ind.last_checked,
                    "stale_after": ind.stale_after,
                    "normalization_method": ind.normalization_method,
                })

        for buf in self.gate_buffers:
            status = buf.get_quality_status(as_of_date=as_of_date)
            if status == "fresh":
                fresh_count += 1
            elif status == "stale":
                stale_count += 1
            else:
                missing_count += 1

            items.append({
                "id": buf.id,
                "name": buf.name,
                "layer": "Gate",
                "status": status,
                "evidence_level": buf.evidence_level,
                "raw_value": buf.raw_value,
                "raw_unit": buf.raw_unit,
                "source_name": buf.source_name or buf.source,
                "source_url": buf.source_url,
                "publication_date": buf.publication_date,
                "last_checked": buf.last_checked,
                "stale_after": buf.stale_after,
                "normalization_method": buf.normalization_method,
            })

        total = len(items)
        # Completeness: percentage of items having valid raw data, source, and normalization method
        complete_count = sum(
            1 for it in items if (it["raw_value"] is not None or it["evidence_level"] == "illustrative") and it["source_name"] and it["normalization_method"]
        )
        completeness_pct = round((complete_count / total * 100.0), 1) if total > 0 else 0.0

        return {
            "as_of_date": as_of_date,
            "total_indicators": total,
            "fresh_count": fresh_count,
            "stale_count": stale_count,
            "missing_count": missing_count,
            "completeness_pct": completeness_pct,
            "items": items,
        }

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
