from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter, Depends

from api.auth import require_auth
from api.schemas import DeletedResource, DeleteResourcesRequest, DeleteResourcesResponse

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/delete-resources",
    tags=["v1"],
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=DeleteResourcesResponse)
async def delete_resources(body: DeleteResourcesRequest) -> DeleteResourcesResponse:
    deleted: list[DeletedResource] = []
    errors: list[str] = []
    base = body.hapi_base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=30.0) as client:
        for res in body.resources:
            url = f"{base}/{res.resource_type}/{res.resource_id}"
            try:
                r = await client.delete(url)
                deleted.append(
                    DeletedResource(
                        resource_type=res.resource_type,
                        resource_id=res.resource_id,
                        status=r.status_code,
                    )
                )
                log.info(
                    "deleted_resource",
                    rtype=res.resource_type,
                    rid=res.resource_id,
                    status=r.status_code,
                )
            except httpx.RequestError as exc:
                errors.append(f"{res.resource_type}/{res.resource_id}: {exc}")
                log.warning(
                    "delete_resource_failed",
                    rtype=res.resource_type,
                    rid=res.resource_id,
                    error=str(exc),
                )

    success_count = sum(1 for d in deleted if d.status in {200, 204})
    return DeleteResourcesResponse(
        deleted=deleted,
        errors=errors,
        total=len(body.resources),
        success_count=success_count,
    )
