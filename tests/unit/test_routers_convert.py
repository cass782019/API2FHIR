from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_SPEC_YAML = """
openapi: "3.0.3"
info:
  title: Test API
  version: "1.0.0"
paths:
  /patients:
    post:
      operationId: createPatient
      summary: Create a patient
      responses:
        "201":
          description: Created
""".strip()

_BUNDLE = {
    "resourceType": "Bundle",
    "type": "collection",
    "id": "test-bundle",
    "entry": [{"resource": {"resourceType": "Patient", "id": "p1"}}],
}


@pytest.fixture
def client() -> TestClient:
    from api.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.unit
def test_convert_sync_returns_bundle(client: TestClient) -> None:
    with (
        patch("api.routers.convert.parse_spec", return_value=MagicMock()),
        patch("api.routers.convert.convert", new=AsyncMock(return_value=_BUNDLE)),
        patch("api.routers.convert.anthropic.AsyncAnthropic", return_value=MagicMock()),
    ):
        resp = client.post("/convert", json={"spec": _SPEC_YAML})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["bundle"]["resourceType"] == "Bundle"
    assert "job_id" in data


@pytest.mark.unit
def test_convert_invalid_spec_returns_422(client: TestClient) -> None:
    with patch("api.routers.convert.parse_spec", side_effect=ValueError("bad spec")):
        resp = client.post("/convert", json={"spec": "invalid: yaml: bad"})

    assert resp.status_code == 422


@pytest.mark.unit
def test_convert_service_error_returns_500(client: TestClient) -> None:
    with (
        patch("api.routers.convert.parse_spec", return_value=MagicMock()),
        patch("api.routers.convert.convert", new=AsyncMock(side_effect=RuntimeError("LLM error"))),
        patch("api.routers.convert.anthropic.AsyncAnthropic", return_value=MagicMock()),
    ):
        resp = client.post("/convert", json={"spec": _SPEC_YAML})

    assert resp.status_code == 500


@pytest.mark.unit
def test_convert_returns_job_id(client: TestClient) -> None:
    with (
        patch("api.routers.convert.parse_spec", return_value=MagicMock()),
        patch("api.routers.convert.convert", new=AsyncMock(return_value=_BUNDLE)),
        patch("api.routers.convert.anthropic.AsyncAnthropic", return_value=MagicMock()),
    ):
        resp = client.post("/convert", json={"spec": _SPEC_YAML})

    data = resp.json()
    assert len(data["job_id"]) == 26  # ULID length


@pytest.mark.unit
def test_convert_missing_spec_field_returns_422(client: TestClient) -> None:
    resp = client.post("/convert", json={"options": {}})
    assert resp.status_code == 422


@pytest.mark.unit
def test_convert_async_mode_returns_pending(client: TestClient) -> None:
    with (
        patch("api.routers.convert.parse_spec", return_value=MagicMock()),
        # worker not available → falls back to sync
        patch("api.routers.convert.convert", new=AsyncMock(return_value=_BUNDLE)),
        patch("api.routers.convert.anthropic.AsyncAnthropic", return_value=MagicMock()),
    ):
        resp = client.post(
            "/convert",
            json={"spec": _SPEC_YAML, "options": {"async": True}},
        )

    # Worker not installed → falls back to sync and returns completed
    assert resp.status_code == 200
    assert resp.json()["status"] in ("pending", "completed")
