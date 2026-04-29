"""Integration: GET /v1/jobs/{id} reads real Redis written by worker actor."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest
import redis as redis_lib


@pytest.mark.integration
@pytest.mark.asyncio
async def test_jobs_endpoint_reads_real_redis(api_client, redis_url: str) -> None:
    """Inject a result into Redis and verify GET /v1/jobs/{id} returns it."""
    bundle_payload = {"resourceType": "Bundle", "type": "collection", "entry": []}
    job_id = "integration-job-001"

    r = redis_lib.Redis.from_url(redis_url, decode_responses=True)
    r.set(
        f"worker:result:{job_id}",
        json.dumps({"status": "completed", "bundle": bundle_payload}),
        ex=3600,
    )

    # Patch the API's _redis() to use the testcontainer Redis URL
    original_url = os.environ.get("REDIS_URL")
    os.environ["REDIS_URL"] = redis_url
    try:
        with patch(
            "api.routers.v1.jobs._redis",
            return_value=redis_lib.Redis.from_url(redis_url, decode_responses=True),
        ):
            resp = await api_client.get(f"/v1/jobs/{job_id}")
    finally:
        if original_url is None:
            os.environ.pop("REDIS_URL", None)
        else:
            os.environ["REDIS_URL"] = original_url

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["bundle"] == bundle_payload
