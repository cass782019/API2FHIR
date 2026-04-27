from __future__ import annotations

from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import require_auth

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/fhir", tags=["fhir"], dependencies=[Depends(require_auth)])


def _hapi_base() -> str:
    from core.settings import settings

    return settings.hapi_base_url


@router.get("/{resource_type}/{resource_id}")
async def proxy_read(resource_type: str, resource_id: str) -> Any:
    """Proxy GET /fhir/{type}/{id} to HAPI."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{_hapi_base()}/{resource_type}/{resource_id}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"{resource_type}/{resource_id} not found")
    resp.raise_for_status()
    return resp.json()


@router.post("/{resource_type}/$validate")
async def proxy_validate(resource_type: str, request: Request) -> Any:
    """Proxy POST /fhir/{type}/$validate to HAPI."""
    body: dict[str, Any] = await request.json()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_hapi_base()}/{resource_type}/$validate",
            json=body,
        )
    return resp.json()
