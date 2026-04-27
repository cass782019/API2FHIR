from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_ok() -> object:
    from api.schemas import ServiceStatus

    return ServiceStatus(ok=True)


def _make_fail(detail: str = "connection refused") -> object:
    from api.schemas import ServiceStatus

    return ServiceStatus(ok=False, detail=detail)


@pytest.fixture
def client() -> TestClient:
    from api.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.unit
def test_health_all_ok(client: TestClient) -> None:
    with (
        patch("api.routers.health._check_hapi", new=AsyncMock(return_value=_make_ok())),
        patch("api.routers.health._check_redis", new=AsyncMock(return_value=_make_ok())),
        patch("api.routers.health._check_postgres", new=AsyncMock(return_value=_make_ok())),
    ):
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["services"]["hapi"]["ok"] is True
    assert data["services"]["redis"]["ok"] is True
    assert data["services"]["postgres"]["ok"] is True


@pytest.mark.unit
def test_health_hapi_down_returns_degraded(client: TestClient) -> None:
    with (
        patch("api.routers.health._check_hapi", new=AsyncMock(return_value=_make_fail("timeout"))),
        patch("api.routers.health._check_redis", new=AsyncMock(return_value=_make_ok())),
        patch("api.routers.health._check_postgres", new=AsyncMock(return_value=_make_ok())),
    ):
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["services"]["hapi"]["ok"] is False


@pytest.mark.unit
def test_health_redis_down_returns_degraded(client: TestClient) -> None:
    with (
        patch("api.routers.health._check_hapi", new=AsyncMock(return_value=_make_ok())),
        patch("api.routers.health._check_redis", new=AsyncMock(return_value=_make_fail())),
        patch("api.routers.health._check_postgres", new=AsyncMock(return_value=_make_ok())),
    ):
        resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


@pytest.mark.unit
def test_health_postgres_down_returns_degraded(client: TestClient) -> None:
    with (
        patch("api.routers.health._check_hapi", new=AsyncMock(return_value=_make_ok())),
        patch("api.routers.health._check_redis", new=AsyncMock(return_value=_make_ok())),
        patch("api.routers.health._check_postgres", new=AsyncMock(return_value=_make_fail())),
    ):
        resp = client.get("/health")

    assert resp.json()["status"] == "degraded"


@pytest.mark.unit
def test_health_response_has_required_fields(client: TestClient) -> None:
    with (
        patch("api.routers.health._check_hapi", new=AsyncMock(return_value=_make_ok())),
        patch("api.routers.health._check_redis", new=AsyncMock(return_value=_make_ok())),
        patch("api.routers.health._check_postgres", new=AsyncMock(return_value=_make_ok())),
    ):
        resp = client.get("/health")

    data = resp.json()
    assert "status" in data
    assert "services" in data
    assert set(data["services"].keys()) == {"hapi", "redis", "postgres"}
