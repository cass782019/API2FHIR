from __future__ import annotations

import anthropic
import structlog
import ulid
from core.settings import settings
from fastapi import APIRouter, Depends, HTTPException, status
from fhir_forge.service import convert
from swagger_lens.parser import parse_spec

from api.auth import require_auth
from api.schemas import ConvertRequest, JobResponse

log = structlog.get_logger(__name__)
router = APIRouter()


@router.post(
    "/convert",
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
    tags=["conversion"],
    dependencies=[Depends(require_auth)],
)
async def convert_spec(body: ConvertRequest) -> JobResponse:
    """Convert an OpenAPI/Swagger spec into a FHIR R4 Bundle.

    Set ``options.async`` to ``true`` to enqueue the conversion as a
    background job (returns immediately with a job_id). Otherwise the
    conversion runs synchronously and the bundle is returned in the response.
    """
    return await _run_conversion(body)


async def _run_conversion(body: ConvertRequest) -> JobResponse:
    """Pure conversion logic — callable from /convert and /v1/convert."""
    try:
        spec = parse_spec(body.spec.encode(), fmt="auto")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid OpenAPI spec: {exc}",
        ) from exc

    job_id = str(ulid.new())

    if body.options.async_mode:
        try:
            from worker.actors.conversion import (
                convert_spec_actor,  # type: ignore[import-not-found]
            )

            convert_spec_actor.send(job_id, body.spec)
            return JobResponse(job_id=job_id, status="pending")
        except (ImportError, RuntimeError):
            log.warning("worker_not_available_falling_back_to_sync")

    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
    )
    try:
        bundle = await convert(
            spec,
            job_id,
            client=client,
            model=body.options.model,
            hapi_base_url=body.options.hapi_base_url,
        )
    except Exception as exc:
        log.error("convert_failed", job_id=job_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Conversion failed: {exc}",
        ) from exc

    return JobResponse(job_id=job_id, status="completed", bundle=bundle)
