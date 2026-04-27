from __future__ import annotations

import asyncio
import json
from typing import Any

import anthropic
import dramatiq
import redis
import structlog
from core.settings import settings
from fhir_forge.service import convert as fhir_service_convert
from swagger_lens.parser import parse_spec

log = structlog.get_logger(__name__)


def _redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url)


async def _run_conversion(job_id: str, swagger_yaml: str) -> dict[str, Any]:
    spec = parse_spec(swagger_yaml.encode(), fmt="auto")
    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
    )
    return await fhir_service_convert(spec, job_id, client=client)


@dramatiq.actor(queue_name="fhir", max_retries=3, time_limit=300_000)
def convert_spec_actor(job_id: str, swagger_yaml: str) -> None:
    r = _redis_client()
    lock_key = f"worker:lock:{job_id}"

    acquired = r.set(lock_key, "processing", nx=True, ex=3600)
    if not acquired:
        log.info("job_already_processing_or_done", job_id=job_id)
        return

    try:
        bundle = asyncio.run(_run_conversion(job_id, swagger_yaml))
        result_key = f"worker:result:{job_id}"
        r.set(result_key, json.dumps({"status": "completed", "bundle": bundle}), ex=86400)
        r.set(lock_key, "completed", ex=86400)
        log.info("job_completed", job_id=job_id)
    except Exception as exc:
        log.error("job_failed", job_id=job_id, error=str(exc))
        r.delete(lock_key)
        raise
