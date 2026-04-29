from __future__ import annotations

from datetime import datetime  # noqa: TC003 — required at runtime by Pydantic
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConvertOptions(BaseModel):
    async_mode: bool = Field(default=False, alias="async")
    auto_infer: bool = False
    model: str = "claude-opus-4-7"
    hapi_base_url: str = "http://localhost:8090/fhir"

    model_config = {"populate_by_name": True}


class ConvertRequest(BaseModel):
    spec: str = Field(
        ...,
        description="OpenAPI/Swagger spec as YAML/JSON string, OR a sample payload "
        "when options.auto_infer=true",
    )
    options: ConvertOptions = Field(default_factory=ConvertOptions)


class JobResponse(BaseModel):
    job_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    bundle: dict[str, Any] | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    errors: list[str] | None = None


class ServiceStatus(BaseModel):
    ok: bool
    detail: str = ""


class HealthResponse(BaseModel):
    status: str
    services: dict[str, ServiceStatus]


class FhirProxyResponse(BaseModel):
    pass


# ── Schemas /v1 ──────────────────────────────────────────────────


class DetectRequest(BaseModel):
    content: str = Field(..., description="JSON or YAML content as string")


class DetectResponse(BaseModel):
    type: Literal["openapi", "swagger", "payload"]
    version: str | None = None


class InferSpecRequest(BaseModel):
    payload: dict[str, Any] = Field(..., description="Sample API response payload")
    resource_name: str = "resource"
    method: str = "POST"


class InferSpecResponse(BaseModel):
    spec: dict[str, Any]
    fabricated: list[str]
    warnings: list[str]


class ValidateSpecRequest(BaseModel):
    spec: dict[str, Any]


class ValidateSpecResponse(BaseModel):
    valid: bool
    errors: list[str]
