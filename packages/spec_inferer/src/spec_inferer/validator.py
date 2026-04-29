from __future__ import annotations

from typing import Any, TypedDict

from openapi_spec_validator import validate as _osv_validate


class ValidationResult(TypedDict):
    valid: bool
    errors: list[str]


def validate_spec(spec: dict[str, Any]) -> ValidationResult:
    """Validate an OpenAPI 3.x spec dict.

    Catches any exception from openapi_spec_validator (its exception hierarchy
    varies between versions 0.5/0.6/0.7). For the caller only valid vs invalid
    + the message matter.
    """
    try:
        _osv_validate(spec)
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)]}
    return {"valid": True, "errors": []}
