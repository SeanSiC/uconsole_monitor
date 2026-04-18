from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


Status = str


@dataclass(slots=True)
class DimensionState:
    status: Status
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "details": self.details,
        }


@dataclass(slots=True)
class Snapshot:
    updated_at: datetime
    host: dict[str, Any]
    dimensions: dict[str, DimensionState]
    overall_status: Status
    overall_summary: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "updated_at": self.updated_at.isoformat(),
            "host": self.host,
            "overall": {
                "status": self.overall_status,
                "summary": self.overall_summary,
            },
            "dimensions": {
                name: state.as_dict() for name, state in self.dimensions.items()
            },
            "warnings": self.warnings,
            "errors": self.errors,
        }
