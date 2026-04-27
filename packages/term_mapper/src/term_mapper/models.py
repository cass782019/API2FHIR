from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Coding:
    """A FHIR Coding element: system + code + optional display."""

    system: str
    code: str
    display: str = ""

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {"system": self.system, "code": self.code}
        if self.display:
            d["display"] = self.display
        return d

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Coding:
        return cls(
            system=data.get("system", ""),
            code=data.get("code", ""),
            display=data.get("display", ""),
        )


@dataclass
class ConceptMatch:
    """A terminology lookup result with confidence score."""

    coding: Coding
    score: float = 1.0
    source: str = ""  # e.g. "snowstorm", "hapi", "cache"
    matched_terms: list[str] = field(default_factory=list)
