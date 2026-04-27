from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from langgraph.graph import END, StateGraph

from fhir_forge.nodes.bundle_node import bundle_node
from fhir_forge.nodes.fix_node import fix_node
from fhir_forge.nodes.mapping_node import mapping_node
from fhir_forge.nodes.parse_node import parse_node
from fhir_forge.nodes.validation_node import validation_node
from fhir_forge.state import ConversionState

if TYPE_CHECKING:
    import anthropic


def _route_validation(state: ConversionState) -> str:
    """Conditional routing after validation_node."""
    if not state["validation_errors"]:
        return "bundle"
    if state["retry_count"] >= 3:
        return "bundle"  # force bundle with warnings
    return "fix"


def build_graph(
    *,
    client: anthropic.AsyncAnthropic | None = None,
    model: str | None = None,
    hapi_base_url: str | None = None,
    checkpointer: Any = None,
) -> Any:
    """Build and compile the ConversionState graph.

    *client*, *model*, and *hapi_base_url* are injected so tests can pass
    mocks without monkeypatching module globals.
    """
    graph: StateGraph = StateGraph(ConversionState)  # type: ignore[type-arg]

    # Bind configurable dependencies via partial
    _mapping = partial(mapping_node, client=client, model=model)
    _validation = partial(validation_node, hapi_base_url=hapi_base_url)
    _fix = partial(fix_node, client=client, model=model)

    graph.add_node("parse", parse_node)
    graph.add_node("map", _mapping)
    graph.add_node("validate", _validation)
    graph.add_node("fix", _fix)
    graph.add_node("bundle", bundle_node)

    graph.set_entry_point("parse")
    graph.add_edge("parse", "map")
    graph.add_edge("map", "validate")
    graph.add_conditional_edges(
        "validate",
        _route_validation,
        {"bundle": "bundle", "fix": "fix"},
    )
    graph.add_edge("fix", "validate")
    graph.add_edge("bundle", END)

    return graph.compile(checkpointer=checkpointer)
