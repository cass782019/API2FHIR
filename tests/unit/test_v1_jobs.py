from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def _mock_redis(*, result: str | None = None, lock: str | None = None) -> MagicMock:
    r = MagicMock()
    r.get.side_effect = lambda key: (
        result if key.startswith("worker:result:") else
        lock if key.startswith("worker:lock:") else None
    )
    return r


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
