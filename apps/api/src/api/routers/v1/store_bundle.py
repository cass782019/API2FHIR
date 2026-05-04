from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter, Depends

from api.auth import require_auth
from api.schemas import StoreBundleRequest, StoreBundleResponse, StoredResource

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/store-bundle", tags=["v1"], dependencies=[Depends(require_auth)])


@router.post("", response_model=StoreBundleResponse)
async def store_bundle(body: StoreBundleRequest) -> StoreBundleResponse:
    stored: list[StoredResource] = []
    errors: list[str] = []
    entries = body.bundle.get("entry", [])

    async with httpx.AsyncClient(timeout=30.0) as client:
        for entry in entries:
            resource = entry.get("resource", {})
            rtype = resource.get("resourceType")
            rid = resource.get("id")
            if not rtype or not rid:
                errors.append("Skipped: missing resourceType or id")
                continue
            url = f"{body.hapi_base_url.rstrip('/')}/{rtype}/{rid}"
            try:
                r = await client.put(
                    url,
                    json=resource,
                    headers={"Content-Type": "application/fhir+json"},
                )
                stored.append(
                    StoredResource(
                        resource_type=rtype,
                        resource_id=rid,
                        fhir_url=url,
                        status=r.status_code,
                    )
                )
                log.info("stored_resource", rtype=rtype, rid=rid, status=r.status_code)
            except httpx.RequestError as exc:
                errors.append(f"{rtype}/{rid}: {exc}")
                log.warning("store_resource_failed", rtype=rtype, rid=rid, error=str(exc))

    success_count = sum(1 for s in stored if s.status in {200, 201})
    return StoreBundleResponse(
        stored=stored,
        errors=errors,
        total=len(entries),
        success_count=success_count,
    )
