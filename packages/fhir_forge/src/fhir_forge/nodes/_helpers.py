from __future__ import annotations

import re
from typing import Any, cast

_SLUG_INVALID = re.compile(r"[^a-z0-9-]+")
_SLUG_DUPDASH = re.compile(r"-{2,}")


def slugify(text: str) -> str:
    """Lowercase slug suitable for FHIR resource ids ([a-z0-9-]+)."""
    if not text:
        return ""
    s = text.lower().replace("_", "-").replace(" ", "-")
    s = _SLUG_INVALID.sub("-", s)
    s = _SLUG_DUPDASH.sub("-", s)
    return s.strip("-")


# Ruff RUF001 flags ambiguous Unicode chars in these markers; the markers ARE
# exactly the literal mojibake byte sequences we want to detect, so suppress.
_MOJIBAKE_MARKERS = (
    "Ã£", "Ã©", "Ã§", "Ã³", "Ã­", "Ãº", "Ã ", "Ã¢", "Ãª", "Ã´",  # noqa: RUF001
    "Ã‡", "Ã‰", "Ãƒ", "Ã“", "Ãš",
)


def repair_mojibake(value: str) -> str:
    """Best-effort UTF-8 repair: try to recover when a string was UTF-8 read as Latin-1."""
    if not isinstance(value, str) or not any(m in value for m in _MOJIBAKE_MARKERS):
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def sanitize_resource(resource: dict[str, Any]) -> dict[str, Any]:
    """Recursively walk a FHIR resource dict, repairing mojibake in string leaves.

    Returns a *new* dict; the input is not mutated.
    """
    return cast("dict[str, Any]", _walk(resource))


def _walk(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _walk(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk(item) for item in node]
    if isinstance(node, str):
        return repair_mojibake(node)
    return node
