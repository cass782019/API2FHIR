from __future__ import annotations

import json
from typing import Any, Literal, TypedDict

import yaml

SpecType = Literal["openapi", "swagger", "payload", "curl"]


class DetectionResult(TypedDict):
    type: SpecType
    version: str | None


def detect_spec_type(content: str | bytes | dict[str, Any]) -> DetectionResult:
    """Determine if the input is an OpenAPI 3.x spec, Swagger 2.0 spec, or a payload."""
    if isinstance(content, dict):
        data: Any = content
    else:
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        text = text.strip()
        if text.startswith("curl "):
            return {"type": "curl", "version": None}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            try:
                data = yaml.safe_load(text)
            except yaml.YAMLError:
                return {"type": "payload", "version": None}

    if not isinstance(data, dict):
        return {"type": "payload", "version": None}

    if "openapi" in data and isinstance(data["openapi"], str):
        return {"type": "openapi", "version": data["openapi"]}
    if "swagger" in data and isinstance(data["swagger"], str):
        return {"type": "swagger", "version": data["swagger"]}
    return {"type": "payload", "version": None}
