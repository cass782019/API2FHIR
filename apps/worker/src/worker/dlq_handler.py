from __future__ import annotations

import json
from typing import Any

import dramatiq
import redis
import structlog
from core.settings import settings

log = structlog.get_logger(__name__)


def _redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url)


def _save_failed(job_id: str, error: str, r: Any) -> None:
    result_key = f"worker:result:{job_id}"
    r.set(result_key, json.dumps({"status": "failed", "error": error}), ex=86400)


@dramatiq.actor(queue_name="fhir_dlq")
def handle_dead_letter(job_id: str, error: str) -> None:
    log.error("job_dead_lettered", job_id=job_id, error=error)
    r = _redis_client()
    _save_failed(job_id, error, r)
