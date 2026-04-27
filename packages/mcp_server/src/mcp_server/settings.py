from __future__ import annotations

from pydantic_settings import BaseSettings


class McpSettings(BaseSettings):
    hapi_base_url: str = "http://localhost:8090/fhir"
    snowstorm_base_url: str = "http://localhost:8080"
    mcp_host: str = "localhost"
    mcp_port: int = 8001
    hapi_timeout: float = 30.0
    snowstorm_timeout: float = 10.0

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = McpSettings()
