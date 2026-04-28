from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _state(
    invalid: list[dict[str, Any]],
    errors: list[str],
    fhir_resources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "swagger_spec": None,
        "endpoints_to_process": [],
        "fhir_resources": fhir_resources or [],
        "invalid_resources": invalid,
        "validation_errors": errors,
        "retry_count": 0,
        "job_id": "fix-job-01",
        "trace_id": "",
        "warnings": [],
    }


def _mock_client(response: dict[str, Any]) -> MagicMock:
    tb = MagicMock()
    tb.text = json.dumps(response)
    msg = MagicMock()
    msg.content = [tb]
    c = MagicMock()
    c.messages = MagicMock()
    c.messages.create = AsyncMock(return_value=msg)
    return c


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fix_node_repairs_mojibake_in_llm_output() -> None:
    from fhir_forge.nodes.fix_node import fix_node

    invalid = [{"resourceType": "Practitioner", "id": "x"}]
    state = _state(invalid, ["x: missing field"])
    client = _mock_client(
        {
            "resourceType": "Practitioner",
            "id": "x",
            "name": [{"family": "JoÃ£o"}],
        }
    )
    out = await fix_node(state, client=client, model="test-model")
    assert out["fhir_resources"][0]["name"][0]["family"] == "João"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fix_node_preserves_id_returned_by_llm() -> None:
    """Semântica intencional: fix_node aceita o id que o LLM devolver.

    O mapping_node já gerou id único antes do fix_node ser chamado, mas se
    o LLM resolver mudar o id durante o fix, fix_node não força o original.
    Documentar para evitar regressão acidental.
    """
    from fhir_forge.nodes.fix_node import fix_node

    invalid = [{"resourceType": "Patient", "id": "booktime", "gender": "wrong"}]
    state = _state(invalid, ["booktime: invalid gender"])
    client = _mock_client(
        {"resourceType": "Patient", "id": "renamed-by-llm", "gender": "female"}
    )
    out = await fix_node(state, client=client, model="test-model")
    assert out["fhir_resources"][0]["id"] == "renamed-by-llm"
    assert out["retry_count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fix_node_invalid_json_keeps_original() -> None:
    """Cobre o branch except MappingError (linhas 84-85)."""
    from fhir_forge.nodes.fix_node import fix_node

    invalid = [{"resourceType": "Patient", "id": "x"}]
    state = _state(invalid, ["x: any error"])
    tb = MagicMock()
    tb.text = "not json"
    msg = MagicMock()
    msg.content = [tb]
    c = MagicMock()
    c.messages = MagicMock()
    c.messages.create = AsyncMock(return_value=msg)

    out = await fix_node(state, client=c, model="test-model")
    # original preservado
    assert out["fhir_resources"] == invalid
    assert out["retry_count"] == 1
