from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    import anthropic
    from swagger_lens.models import SwaggerSpec

log = structlog.get_logger(__name__)


async def convert(
    swagger_spec: SwaggerSpec,
    job_id: str,
    *,
    client: anthropic.AsyncAnthropic | None = None,
    model: str | None = None,
    hapi_base_url: str | None = None,
    checkpointer: Any = None,
) -> dict[str, Any]:
    """Convert a SwaggerSpec into a FHIR R4 Bundle dict.

    Returns the Bundle dict assembled by bundle_node.
    Raises MappingError / SpecParseError on unrecoverable failures.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from fhir_forge.graph import build_graph

    if checkpointer is None:
        checkpointer = MemorySaver()

    compiled = build_graph(
        client=client,
        model=model,
        hapi_base_url=hapi_base_url,
        checkpointer=checkpointer,
    )

    initial_state: dict[str, Any] = {
        "swagger_spec": swagger_spec,
        "endpoints_to_process": [],
        "fhir_resources": [],
        "invalid_resources": [],
        "validation_errors": [],
        "retry_count": 0,
        "job_id": job_id,
        "trace_id": "",
        "warnings": [],
    }

    config = {"configurable": {"thread_id": job_id}}
    final_state: dict[str, Any] = await compiled.ainvoke(initial_state, config=config)

    bundle: dict[str, Any] | None = final_state.get("_bundle")
    if bundle is None:
        # Fallback — should not happen if graph is correctly wired
        bundle = {
            "resourceType": "Bundle",
            "id": f"forge-{job_id}",
            "type": "collection",
            "entry": [
                {"resource": r} for r in final_state.get("fhir_resources", [])
            ],
        }

    log.info(
        "conversion_complete",
        job_id=job_id,
        entry_count=len(bundle.get("entry", [])),
        warnings=len(final_state.get("warnings", [])),
    )
    return bundle
