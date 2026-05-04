from __future__ import annotations

import json

import ulid
from core.settings import settings
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis as AsyncRedis

from api.auth import require_auth
from api.schemas import JobResponse

router = APIRouter(prefix="/jobs", tags=["v1"], dependencies=[Depends(require_auth)])


def _redis() -> AsyncRedis:
    return AsyncRedis.from_url(settings.redis_url, decode_responses=True)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """Poll the status of an async conversion job.

    Bundle results are persisted by `worker.actors.conversion.convert_spec_actor`
    in Redis at ``worker:result:{job_id}`` with TTL 86400s (24h).
    A processing job has only ``worker:lock:{job_id}`` set.
    """
    r = _redis()
    result_raw = await r.get(f"worker:result:{job_id}")
    lock_raw = await r.get(f"worker:lock:{job_id}")

    if result_raw:
        data = json.loads(result_raw)
        return JobResponse(
            job_id=job_id,
            status=data.get("status", "completed"),
            bundle=data.get("bundle"),
            errors=data.get("errors"),
            replayable=data.get("replayable"),
        )
    if lock_raw == "processing":
        return JobResponse(job_id=job_id, status="processing")
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Job {job_id} not found",
    )


@router.post("/{job_id}/replay", response_model=JobResponse)
async def replay_job(job_id: str) -> JobResponse:
    """Re-enqueue a failed job using its saved payload.

    Requires that the original payload was persisted in Redis at
    ``worker:payload:{job_id}`` (TTL 7 days). Returns 404 if the payload
    has expired or was never saved.
    """
    r = _redis()
    raw_payload = await r.get(f"worker:payload:{job_id}")
    if not raw_payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payload not found or expired — cannot replay this job",
        )

    new_job_id = str(ulid.new())
    await r.set(f"worker:payload:{new_job_id}", raw_payload, ex=86400 * 7)

    try:
        from worker.actors.conversion import (  # type: ignore[import-not-found]
            convert_spec_actor,
        )

        convert_spec_actor.send(new_job_id, raw_payload)
    except (ImportError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Worker not available — cannot enqueue replay",
        ) from exc

    return JobResponse(job_id=new_job_id, status="pending")
