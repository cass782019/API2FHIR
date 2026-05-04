from __future__ import annotations

from core.exceptions import FhirForgeError


class SpecParseError(FhirForgeError):
    """Raised when an OpenAPI spec cannot be parsed or validated."""
