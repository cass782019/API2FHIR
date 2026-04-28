from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import structlog
from core.exceptions import MappingError

from fhir_forge.nodes._helpers import sanitize_resource

if TYPE_CHECKING:
    import anthropic

    from fhir_forge.state import ConversionState

log = structlog.get_logger(__name__)

_FIX_SYSTEM = """\
You are a FHIR R4 expert. You will receive a FHIR resource JSON that failed HAPI $validate \
and the list of validation errors.
Fix the resource so it is valid FHIR R4.
Return ONLY the corrected JSON object — no markdown, no explanation.
Use proper UTF-8 for accented characters; never emit mojibake (e.g. "Ã£", "Ã©").
"""


async def _fix_resource(
    client: anthropic.AsyncAnthropic,
    model: str,
    resource: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    prompt = (
        f"Resource (failed validation):\n{json.dumps(resource, indent=2)}\n\n"
        f"Validation errors:\n" + "\n".join(f"- {e}" for e in errors)
    )
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=_FIX_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw: str = response.content[0].text  # type: ignore[union-attr]
    raw = re.sub(r"^```(?:json)?\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        fixed: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MappingError(
            "LLM fix returned invalid JSON",
            endpoint=resource.get("id", ""),
            reason=str(exc),
        ) from exc
    return fixed


async def fix_node(
    state: ConversionState,
    *,
    client: anthropic.AsyncAnthropic | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Ask the LLM to fix resources that failed HAPI validation."""
    from core.llm_router import LLMProvider, LLMRouter
    from core.settings import settings as app_settings

    if client is None:
        router = LLMRouter(app_settings)
        client = router.get_anthropic_client()
    if model is None:
        router = LLMRouter(app_settings)
        model = router.model_id(LLMProvider.ANTHROPIC)

    invalid = state["invalid_resources"]
    errors = state["validation_errors"]
    fixed: list[dict[str, Any]] = []

    for resource in invalid:
        rid = resource.get("id", resource.get("resourceType", "?"))
        resource_errors = [e for e in errors if e.startswith(f"{rid}:")]
        try:
            result = await _fix_resource(client, model, resource, resource_errors)
            result = sanitize_resource(result)
            fixed.append(result)
            log.info("resource_fixed", resource_id=rid)
        except MappingError as exc:
            log.warning("fix_failed", resource_id=rid, reason=str(exc))
            fixed.append(resource)  # keep original; validation will reject again

    return {
        "fhir_resources": state["fhir_resources"] + fixed,
        "invalid_resources": [],
        "validation_errors": [],
        "retry_count": state["retry_count"] + 1,
    }
