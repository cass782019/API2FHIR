from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from spec_inferer.inferer import infer_openapi_from_payload

from api.auth import require_auth
from api.schemas import InferSpecRequest, InferSpecResponse

_VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

router = APIRouter(prefix="/infer-spec", tags=["v1"], dependencies=[Depends(require_auth)])


@router.post("", response_model=InferSpecResponse)
async def infer(body: InferSpecRequest) -> InferSpecResponse:
    if body.method.upper() not in _VALID_METHODS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid HTTP method: {body.method}",
        )
    result = infer_openapi_from_payload(
        body.payload,
        resource_name=body.resource_name,
        method=body.method,
    )
    return InferSpecResponse(
        spec=result["spec"],
        fabricated=result["fabricated"],
        warnings=result["warnings"],
    )
