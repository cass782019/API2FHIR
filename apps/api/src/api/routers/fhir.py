from __future__ import annotations

from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.auth import require_auth

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/fhir", tags=["fhir"], dependencies=[Depends(require_auth)])


def _hapi_base() -> str:
    from core.settings import settings

    return settings.hapi_base_url


@router.get("/{resource_type}")
async def proxy_search(
    resource_type: str,
    request: Request,
    hapi_base_url: str | None = Query(default=None),
) -> Any:
    """Proxy GET /fhir/{type}?params → HAPI (busca de coleção).

    hapi_base_url: substitui a URL configurada em settings (para Gerenciar/Testes).
    """
    base = (hapi_base_url or _hapi_base()).rstrip("/")
    params = {k: v for k, v in request.query_params.items() if k != "hapi_base_url"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{base}/{resource_type}", params=params)
    if resp.status_code == 404:
        return {"resourceType": "Bundle", "type": "searchset", "total": 0, "entry": []}
    resp.raise_for_status()
    return resp.json()


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
