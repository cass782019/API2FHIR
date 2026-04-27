from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConvertOptions(BaseModel):
    async_mode: bool = Field(default=False, alias="async")
    model: str = "claude-opus-4-7"
    hapi_base_url: str = "http://localhost:8090/fhir"

    model_config = {"populate_by_name": True}


class ConvertRequest(BaseModel):
    spec: str = Field(..., description="OpenAPI/Swagger spec as YAML or JSON string")
    options: ConvertOptions = Field(default_factory=ConvertOptions)


class JobResponse(BaseModel):
    job_id: str
    status: str
    bundle: dict[str, Any] | None = None


class ServiceStatus(BaseModel):
    ok: bool
    detail: str = ""


class HealthResponse(BaseModel):
    status: str
    services: dict[str, ServiceStatus]


class FhirProxyResponse(BaseModel):
    pass
