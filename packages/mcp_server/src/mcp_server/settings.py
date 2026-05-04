from __future__ import annotations

from pydantic_settings import BaseSettings


class McpSettings(BaseSettings):
    # hapi_base_url and snowstorm_base_url are inherited from core.settings
    # to avoid silent divergence between the MCP server and the API.
    mcp_host: str = "localhost"
    mcp_port: int = 8001
    hapi_timeout: float = 30.0
    snowstorm_timeout: float = 10.0

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = McpSettings()
