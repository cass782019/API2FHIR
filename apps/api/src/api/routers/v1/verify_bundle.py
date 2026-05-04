from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter, Depends

from api.auth import require_auth
from api.schemas import VerifiedResource, VerifyBundleRequest, VerifyBundleResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/verify-bundle", tags=["v1"], dependencies=[Depends(require_auth)])


@router.post("", response_model=VerifyBundleResponse)
async def verify_bundle(body: VerifyBundleRequest) -> VerifyBundleResponse:
    results: list[VerifiedResource] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for s in body.stored:
            base = body.hapi_base_url.rstrip("/")
            url = f"{base}/{s.resource_type}/{s.resource_id}"

            # GET — verifica existência
            resource_json: dict = {}
            try:
                r_get = await client.get(url)
                get_status = r_get.status_code
                if get_status == 200:
                    resource_json = r_get.json()
            except httpx.RequestError as exc:
                log.warning("verify_get_failed", url=url, error=str(exc))
                get_status = 0

            # $validate — só se GET 200
            valid: bool | None = None
            issues: list[dict] = []
            if get_status == 200 and resource_json:
                try:
                    val_url = f"{base}/{s.resource_type}/$validate"
                    params: dict[str, str] = {}
                    if body.profile_url:
                        params["profile"] = body.profile_url
                    rv = await client.post(
                        val_url,
                        json=resource_json,
                        params=params,
                        headers={"Content-Type": "application/fhir+json"},
                    )
                    outcome = rv.json()
                    issues = outcome.get("issue", [])
                    valid = all(
                        i.get("severity") not in {"error", "fatal"} for i in issues
                    )
                except Exception as exc:
                    log.warning("verify_validate_failed", url=val_url, error=str(exc))

            results.append(
                VerifiedResource(
                    resource_type=s.resource_type,
                    resource_id=s.resource_id,
                    fhir_url=url,
                    get_status=get_status,
                    valid=valid,
                    issues=issues,
                )
            )
            log.info(
                "verified_resource",
                rtype=s.resource_type,
                rid=s.resource_id,
                get_status=get_status,
                valid=valid,
            )

    return VerifyBundleResponse(
        results=results,
        all_accessible=all(r.get_status == 200 for r in results),
        all_valid=all(r.valid is True for r in results),
    )
