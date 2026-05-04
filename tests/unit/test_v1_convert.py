from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

_VALID_SPEC = json.dumps({
    "openapi": "3.0.3",
    "info": {"title": "x", "version": "0.1.0"},
    "paths": {},
})

_PAYLOAD = json.dumps({"id": 1, "name": "Maria"})


def _stub_job_response() -> AsyncMock:
    """Returns a mock that pretends _run_conversion completed sync."""
    from api.schemas import JobResponse

    async def _ret(body, **kwargs):
        return JobResponse(
            job_id="01STUB",
            status="completed",
            bundle={"resourceType": "Bundle", "type": "collection", "entry": []},
        )

    return AsyncMock(side_effect=_ret)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_v1_convert_with_real_spec_passes_through(api_client) -> None:
    """auto_infer=false (default): spec não é tocado, _run_conversion chamado uma vez."""
    stub = _stub_job_response()
    with patch("api.routers.v1.convert._run_conversion", new=stub):
        r = await api_client.post(
            "/v1/convert",
            json={"spec": _VALID_SPEC, "options": {"async": False}},
        )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    stub.assert_called_once()
    forwarded_body = stub.call_args[0][0]
    assert forwarded_body.spec == _VALID_SPEC  # unchanged


@pytest.mark.unit
@pytest.mark.asyncio
async def test_v1_convert_auto_infer_payload_replaces_spec(api_client) -> None:
    """auto_infer=true + payload: spec é substituído pelo inferido antes de delegar."""
    stub = _stub_job_response()
    with patch("api.routers.v1.convert._run_conversion", new=stub):
        r = await api_client.post(
            "/v1/convert",
            json={"spec": _PAYLOAD, "options": {"async": False, "auto_infer": True}},
        )
    assert r.status_code == 200
    stub.assert_called_once()
    forwarded_body = stub.call_args[0][0]
    forwarded_spec = json.loads(forwarded_body.spec)
    # OpenAPI 3.0.3 inferido
    assert forwarded_spec["openapi"] == "3.0.3"
    assert "/resources" in forwarded_spec["paths"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_v1_convert_auto_infer_with_real_spec_passes_through(api_client) -> None:
    """auto_infer=true + spec real: detector retorna 'openapi', spec não muda."""
    stub = _stub_job_response()
    with patch("api.routers.v1.convert._run_conversion", new=stub):
        r = await api_client.post(
            "/v1/convert",
            json={"spec": _VALID_SPEC, "options": {"async": False, "auto_infer": True}},
        )
    assert r.status_code == 200
    forwarded_body = stub.call_args[0][0]
    assert forwarded_body.spec == _VALID_SPEC  # not replaced


@pytest.mark.unit
@pytest.mark.asyncio
async def test_v1_convert_curl_input_returns_422(api_client) -> None:
    """auto_infer=true + curl command: deve retornar 422 com mensagem clara."""
    stub = _stub_job_response()
    curl_cmd = "curl --request GET --url https://api.example.com/patients --header 'accept: application/json'"
    with patch("api.routers.v1.convert._run_conversion", new=stub):
        r = await api_client.post(
            "/v1/convert",
            json={"spec": curl_cmd, "options": {"async": False, "auto_infer": True}},
        )
    assert r.status_code == 422
    assert "curl" in r.text.lower()
    stub.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_v1_convert_non_dict_payload_returns_422(api_client) -> None:
    """auto_infer=true + payload que não é dict/list: deve retornar 422."""
    stub = _stub_job_response()
    with patch("api.routers.v1.convert._run_conversion", new=stub):
        r = await api_client.post(
            "/v1/convert",
            json={"spec": '"just a string"', "options": {"async": False, "auto_infer": True}},
        )
    assert r.status_code == 422
    stub.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_v1_convert_inferred_spec_validation_fail_returns_422(api_client) -> None:
    """Mock o validator pra retornar inválido — endpoint deve responder 422."""
    stub = _stub_job_response()
    with (
        patch("api.routers.v1.convert._run_conversion", new=stub),
        patch(
            "api.routers.v1.convert.validate_spec",
            return_value={"valid": False, "errors": ["forced error"]},
        ),
    ):
        r = await api_client.post(
            "/v1/convert",
            json={"spec": _PAYLOAD, "options": {"async": False, "auto_infer": True}},
        )
    assert r.status_code == 422
    assert "forced error" in r.text
    stub.assert_not_called()
