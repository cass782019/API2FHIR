from __future__ import annotations

import json

from core.settings import settings
from fastapi import APIRouter, Depends, HTTPException, status
from redis import Redis

from api.auth import require_auth
from api.schemas import JobResponse

router = APIRouter(prefix="/jobs", tags=["v1"], dependencies=[Depends(require_auth)])


def _redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """Poll the status of an async conversion job.

    Bundle results are persisted by `worker.actors.conversion.convert_spec_actor`
    in Redis at ``worker:result:{job_id}`` with TTL 86400s (24h).
    A processing job has only ``worker:lock:{job_id}`` set.
    """
    r = _redis()
    result_raw = r.get(f"worker:result:{job_id}")
    lock_raw = r.get(f"worker:lock:{job_id}")

    if result_raw:
        data = json.loads(result_raw)
        return JobResponse(
            job_id=job_id,
            status=data.get("status", "completed"),
            bundle=data.get("bundle"),
            errors=data.get("errors"),
        )
    if lock_raw == "processing":
        return JobResponse(job_id=job_id, status="processing")
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Job {job_id} not found",
    )
