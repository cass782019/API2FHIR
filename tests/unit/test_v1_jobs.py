from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio import Redis as AsyncRedis


def _mock_redis(*, result: str | None = None, lock: str | None = None) -> MagicMock:
    r = MagicMock(spec=AsyncRedis)

    async def _get(key: str) -> str | None:
        if key.startswith("worker:result:"):
            return result
        if key.startswith("worker:lock:"):
            return lock
        return None

    r.get = _get
    r.set = AsyncMock(return_value=True)
    return r


@pytest.mark.unit
def test_redis_factory_returns_async_redis() -> None:
    """_redis() deve retornar instância AsyncRedis (não Redis síncrono)."""
    from api.routers.v1.jobs import _redis

    r = _redis()
    assert isinstance(r, AsyncRedis)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jobs_returns_completed_when_result_exists(api_client) -> None:
    payload = json.dumps({"status": "completed", "bundle": {"resourceType": "Bundle", "entry": []}})
    with patch("api.routers.v1.jobs._redis", return_value=_mock_redis(result=payload)):
        r = await api_client.get("/v1/jobs/abc123")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["bundle"] == {"resourceType": "Bundle", "entry": []}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jobs_returns_processing_when_lock_exists(api_client) -> None:
    with patch("api.routers.v1.jobs._redis", return_value=_mock_redis(lock="processing")):
        r = await api_client.get("/v1/jobs/abc123")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "processing"
    assert data["bundle"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jobs_returns_404_when_neither_exists(api_client) -> None:
    with patch("api.routers.v1.jobs._redis", return_value=_mock_redis()):
        r = await api_client.get("/v1/jobs/nonexistent")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jobs_returns_failed_with_errors(api_client) -> None:
    payload = json.dumps({"status": "failed", "errors": ["LLM timeout"]})
    with patch("api.routers.v1.jobs._redis", return_value=_mock_redis(result=payload)):
        r = await api_client.get("/v1/jobs/xyz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "failed"
    assert data["errors"] == ["LLM timeout"]
    assert data["bundle"] is None
