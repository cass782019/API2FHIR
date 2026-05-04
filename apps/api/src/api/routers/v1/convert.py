from __future__ import annotations

import json

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, status
from spec_inferer.detector import detect_spec_type
from spec_inferer.inferer import infer_openapi_from_payload
from spec_inferer.validator import validate_spec

from api.auth import require_auth
from api.routers.convert import _run_conversion
from api.schemas import ConvertRequest, JobResponse

router = APIRouter(prefix="/convert", tags=["v1"], dependencies=[Depends(require_auth)])


@router.post("", response_model=JobResponse)
async def convert_v1(body: ConvertRequest, request: Request) -> JobResponse:
    """Versioned wrapper for /convert with optional auto_infer.

    When ``options.auto_infer=true`` and ``body.spec`` is a JSON payload
    (no ``openapi``/``swagger`` field), the spec is inferred from it before
    running the standard conversion. Otherwise behaves identically to /convert.
    """
    if body.options.auto_infer:
        detection = detect_spec_type(body.spec)
        if detection["type"] == "curl":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Entrada inválida: parece ser um comando curl. "
                    "Envie o corpo JSON da resposta da API (payload) "
                    "ou uma especificação OpenAPI/Swagger."
                ),
            )
        if detection["type"] == "payload":
            try:
                payload = json.loads(body.spec)
            except json.JSONDecodeError:
                payload = yaml.safe_load(body.spec)
            if not isinstance(payload, (dict, list)):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Não foi possível inferir spec: o conteúdo não é um "
                        "objeto ou array JSON válido."
                    ),
                )
            inferred = infer_openapi_from_payload(payload)
            validation = validate_spec(inferred["spec"])
            if not validation["valid"]:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Inferred spec failed validation: {validation['errors']}",
                )
            body.spec = json.dumps(inferred["spec"])

    checkpointer = getattr(request.app.state, "checkpointer", None)
    return await _run_conversion(body, checkpointer=checkpointer)
