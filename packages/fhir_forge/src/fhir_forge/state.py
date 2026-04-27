from __future__ import annotations

from typing import Any, TypedDict


class ConversionState(TypedDict, total=False):
    swagger_spec: Any  # swagger_lens.models.SwaggerSpec (Any avoids runtime eval by LangGraph)
    endpoints_to_process: list[str]  # operation_ids remaining
    fhir_resources: list[dict[str, Any]]
    invalid_resources: list[dict[str, Any]]  # resources that failed validation
    validation_errors: list[str]
    retry_count: int
    job_id: str
    trace_id: str
    warnings: list[str]
    _bundle: dict[str, Any]  # assembled by bundle_node; read by service.py
