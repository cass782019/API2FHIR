from __future__ import annotations

from fastapi import APIRouter, Depends
from spec_inferer.detector import detect_spec_type

from api.auth import require_auth
from api.schemas import DetectRequest, DetectResponse

router = APIRouter(prefix="/detect", tags=["v1"], dependencies=[Depends(require_auth)])


@router.post("", response_model=DetectResponse)
async def detect(body: DetectRequest) -> DetectResponse:
    result = detect_spec_type(body.content)
    return DetectResponse(type=result["type"], version=result["version"])
