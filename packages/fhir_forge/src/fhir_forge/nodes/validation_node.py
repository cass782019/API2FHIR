from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog
from core.settings import settings as app_settings

if TYPE_CHECKING:
    from fhir_forge.state import ConversionState

log = structlog.get_logger(__name__)


async def _validate_resource(
    resource: dict[str, Any],
    hapi_base_url: str,
) -> list[str]:
    """POST /$validate against HAPI. Returns list of error/fatal issue messages."""
    resource_type = resource.get("resourceType", "Resource")
    url = f"{hapi_base_url}/{resource_type}/$validate"
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(url, json=resource)
    except httpx.RequestError as exc:
        return [f"HAPI unreachable: {exc}"]

    outcome: dict[str, Any] = resp.json()
    errors: list[str] = []
    for issue in outcome.get("issue", []):
        severity = issue.get("severity", "")
        if severity in ("error", "fatal"):
            diag = issue.get("diagnostics", issue.get("details", {}).get("text", "unknown"))
            errors.append(f"[{severity}] {diag}")
    return errors


async def validation_node(
    state: ConversionState,
    *,
    hapi_base_url: str | None = None,
) -> dict[str, Any]:
    """Validate each FHIR resource in state against HAPI's $validate endpoint."""
    base_url = hapi_base_url or app_settings.hapi_base_url
    resources = state["fhir_resources"]

    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    all_errors: list[str] = []

    for resource in resources:
        errors = await _validate_resource(resource, base_url)
        if errors:
            invalid.append(resource)
            rid = resource.get("id", resource.get("resourceType", "?"))
            all_errors.extend(f"{rid}: {e}" for e in errors)
            log.warning("validation_errors", resource_id=rid, error_count=len(errors))
        else:
            valid.append(resource)
            log.info("resource_valid", resource_id=resource.get("id"))

    return {
        "fhir_resources": valid,
        "invalid_resources": invalid,
        "validation_errors": all_errors,
    }
