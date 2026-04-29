from __future__ import annotations

from fastapi import APIRouter, Depends
from spec_inferer.validator import validate_spec

from api.auth import require_auth
from api.schemas import ValidateSpecRequest, ValidateSpecResponse

router = APIRouter(prefix="/validate-spec", tags=["v1"], dependencies=[Depends(require_auth)])


@router.post("", response_model=ValidateSpecResponse)
async def validate(body: ValidateSpecRequest) -> ValidateSpecResponse:
    result = validate_spec(body.spec)
    return ValidateSpecResponse(valid=result["valid"], errors=result["errors"])
