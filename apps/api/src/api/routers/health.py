from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter

from api.schemas import HealthResponse, ServiceStatus

log = structlog.get_logger(__name__)
router = APIRouter()


async def _check_hapi(base_url: str) -> ServiceStatus:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/metadata")
        return ServiceStatus(ok=resp.status_code < 400)
    except Exception as exc:
        return ServiceStatus(ok=False, detail=str(exc))


async def _check_redis(redis_url: str) -> ServiceStatus:
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(redis_url)
        await r.ping()  # type: ignore[misc]
        await r.aclose()
        return ServiceStatus(ok=True)
    except Exception as exc:
        return ServiceStatus(ok=False, detail=str(exc))


async def _check_postgres(dsn: str) -> ServiceStatus:
    try:
        import psycopg

        aconn = await psycopg.AsyncConnection.connect(
            dsn.replace("postgresql+psycopg://", "postgresql://"),
            connect_timeout=5,
        )
        await aconn.close()
        return ServiceStatus(ok=True)
    except Exception as exc:
        return ServiceStatus(ok=False, detail=str(exc))


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    from core.settings import settings

    hapi_status, redis_status, pg_status = (
        await _check_hapi(settings.hapi_base_url),
        await _check_redis(settings.redis_url),
        await _check_postgres(settings.postgres_dsn),
    )

    all_ok = hapi_status.ok and redis_status.ok and pg_status.ok
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        services={
            "hapi": hapi_status,
            "redis": redis_status,
            "postgres": pg_status,
        },
    )
