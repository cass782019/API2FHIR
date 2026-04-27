from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import structlog
from core.exceptions import MappingError

if TYPE_CHECKING:
    import anthropic

    from fhir_forge.state import ConversionState

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a FHIR R4 expert specialising in Brazilian health interoperability (BR Core v1, RNDS).
Your task: given one API endpoint, generate a single, minimal, VALID FHIR R4 resource JSON \
that represents the primary data entity managed by that endpoint.

Rules:
- Return ONLY a JSON object — no markdown fences, no explanation.
- The JSON must include "resourceType" and "id".
- Use realistic but synthetic data (no real CPFs or CNSs).
- For Patient: include identifier array with CPF \
  (system "https://rnds.saude.gov.br/fhir/NamingSystem/cpf") and \
  CNS (system "https://rnds.saude.gov.br/fhir/NamingSystem/cns").
- For Encounter: include "status", "class", and "subject".
- For Observation: include "status", "code" (LOINC), "subject", and "valueQuantity".
- If the endpoint does not map to a FHIR resource, return {"resourceType": "Basic", "id": "n/a"}.
"""

_FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "content": "Endpoint: POST /patients | createPatient | Create a new patient record | tags: patient",
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "resourceType": "Patient",
                "id": "createPatient-example",
                "meta": {"profile": ["http://www.saude.gov.br/fhir/r4/StructureDefinition/BRIndividuo-1.0"]},
                "identifier": [
                    {
                        "system": "https://rnds.saude.gov.br/fhir/NamingSystem/cpf",
                        "value": "123.456.789-09",
                    },
                    {
                        "system": "https://rnds.saude.gov.br/fhir/NamingSystem/cns",
                        "value": "700.000.000-0001",
                    },
                ],
                "name": [{"use": "official", "family": "Silva", "given": ["Maria", "Aparecida"]}],
                "gender": "female",
                "birthDate": "1985-03-15",
            }
        ),
    },
    {
        "role": "user",
        "content": "Endpoint: POST /encounters | createEncounter | Register a new encounter | tags: encounter",
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "resourceType": "Encounter",
                "id": "createEncounter-example",
                "status": "finished",
                "class": {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "AMB",
                    "display": "ambulatory",
                },
                "subject": {"reference": "Patient/patient-example"},
                "period": {"start": "2024-01-15T09:00:00-03:00", "end": "2024-01-15T09:30:00-03:00"},
            }
        ),
    },
]


def _build_user_prompt(endpoint: Any) -> str:  # endpoint: swagger_lens.models.Endpoint
    tags = ", ".join(endpoint.tags) if endpoint.tags else "none"
    return (
        f"Endpoint: {endpoint.method} {endpoint.path} | "
        f"{endpoint.operation_id} | {endpoint.summary} | tags: {tags}"
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from an LLM text response."""
    text = text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        # Try to find JSON object inside the text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())  # type: ignore[no-any-return]
        raise


async def _map_endpoint(
    client: anthropic.AsyncAnthropic,
    model: str,
    endpoint: Any,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        *_FEW_SHOT_EXAMPLES,
        {"role": "user", "content": _build_user_prompt(endpoint)},
    ]
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=messages,  # type: ignore[arg-type]
    )
    raw_text: str = response.content[0].text  # type: ignore[union-attr]
    try:
        resource = _extract_json(raw_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise MappingError(
            f"LLM returned invalid JSON for {endpoint.operation_id}",
            endpoint=endpoint.path,
            reason=str(exc),
        ) from exc
    if "resourceType" not in resource:
        raise MappingError(
            f"LLM response missing resourceType for {endpoint.operation_id}",
            endpoint=endpoint.path,
            reason="missing resourceType",
        )
    return resource


async def mapping_node(
    state: ConversionState,
    *,
    client: anthropic.AsyncAnthropic | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Map all endpoints in `endpoints_to_process` to FHIR resource dicts.

    *client* and *model* are injected by the graph (via partial) so tests can
    pass a mock without patching at the module level.
    """
    from core.llm_router import LLMProvider, LLMRouter
    from core.settings import settings as app_settings

    spec = state["swagger_spec"]
    op_ids = state["endpoints_to_process"]

    if client is None:
        router = LLMRouter(app_settings)
        client = router.get_anthropic_client()
    if model is None:
        router = LLMRouter(app_settings)
        model = router.model_id(LLMProvider.ANTHROPIC)

    endpoint_map = {ep.operation_id: ep for ep in spec.endpoints}
    resources: list[dict[str, Any]] = []

    for op_id in op_ids:
        ep = endpoint_map.get(op_id)
        if ep is None:
            continue
        try:
            resource = await _map_endpoint(client, model, ep)
            # Skip Basic placeholders
            if resource.get("resourceType") != "Basic":
                resources.append(resource)
                log.info("mapped_endpoint", op_id=op_id, resource_type=resource["resourceType"])
        except MappingError as exc:
            log.warning("mapping_failed", op_id=op_id, reason=str(exc))

    return {
        "fhir_resources": resources,
        "endpoints_to_process": [],
    }
