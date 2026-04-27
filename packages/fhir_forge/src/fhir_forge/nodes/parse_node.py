from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fhir_forge.state import ConversionState


def parse_node(state: ConversionState) -> dict[str, Any]:
    """Extract the ordered list of operation_ids to process.

    Prioritises endpoints that have FHIR hints (patient, encounter, etc.) and
    avoids no-op paths like /health, /metrics.
    """
    from swagger_lens.extractor import extract_fhir_hints

    spec = state["swagger_spec"]
    skip_patterns = {"health", "metrics", "ping", "status", "version", "ready", "live"}

    prioritised: list[str] = []
    rest: list[str] = []

    for ep in spec.endpoints:
        path_lower = ep.path.lower()
        op_lower = ep.operation_id.lower()
        if any(p in path_lower or p in op_lower for p in skip_patterns):
            continue
        hints = extract_fhir_hints(ep)
        if hints:
            prioritised.append(ep.operation_id)
        else:
            rest.append(ep.operation_id)

    return {"endpoints_to_process": prioritised + rest}
