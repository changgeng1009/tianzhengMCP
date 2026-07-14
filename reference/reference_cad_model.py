from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReferenceCADModel:
    source: dict[str, Any]
    entities: list[dict[str, Any]]
    layers: list[dict[str, Any]] = field(default_factory=list)
    global_uncertainties: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReferenceCADModel":
        return cls(
            source=dict(data.get("source", {"kind": "reference_dwg"})),
            layers=list(data.get("layers", [])),
            global_uncertainties=list(data.get("global_uncertainties", [])),
            entities=[dict(entity) for entity in data.get("entities", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": dict(self.source),
            "layers": list(self.layers),
            "global_uncertainties": list(self.global_uncertainties),
            "entities": [dict(entity) for entity in self.entities],
        }
