from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SchemaRef:
    """Resolved schema fragment — either an inline dict or a resolved $ref."""

    raw: dict[str, Any]
    ref_path: str | None = None


@dataclass
class Parameter:
    name: str
    location: str  # "query", "path", "header", "cookie", "body" (OAS2 formData → body)
    required: bool = False
    schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class Endpoint:
    path: str
    method: str  # uppercase: GET, POST, PUT, PATCH, DELETE
    operation_id: str
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    params: list[Parameter] = field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, Any] = field(default_factory=dict)


@dataclass
class SwaggerSpec:
    title: str
    version: str
    base_url: str
    openapi_version: str  # e.g. "2.0", "3.0.3", "3.1.0"
    endpoints: list[Endpoint] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
