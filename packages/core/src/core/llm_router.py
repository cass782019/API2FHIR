from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

import anthropic

from .exceptions import ConfigurationError

if TYPE_CHECKING:
    from .settings import Settings


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    OPENAI = "openai"
    MARITACA = "maritaca"
    VLLM = "vllm-onprem"


class LLMRouter:
    """Routes LLM requests to the correct provider based on PHI policy and config.

    PHI routing rule: if phi_data=True and FEATURE_ALLOW_PHI_EGRESS=False,
    always use vLLM on-prem regardless of LLM_DEFAULT_ROUTE.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def selected_provider(self, phi_data: bool) -> LLMProvider:
        """Return the provider that should handle this request."""
        if phi_data and not self._settings.feature_allow_phi_egress:
            return LLMProvider.VLLM
        try:
            return LLMProvider(self._settings.llm_default_route)
        except ValueError:
            return LLMProvider.ANTHROPIC

    def get_anthropic_client(self, fast: bool = False) -> anthropic.AsyncAnthropic:
        key = self._settings.anthropic_api_key.get_secret_value()
        if not key:
            raise ConfigurationError("ANTHROPIC_API_KEY not set")
        return anthropic.AsyncAnthropic(api_key=key)

    def model_id(self, provider: LLMProvider, fast: bool = False) -> str:
        """Return the model ID string for the given provider."""
        match provider:
            case LLMProvider.ANTHROPIC:
                return (
                    self._settings.anthropic_model_fast
                    if fast
                    else self._settings.anthropic_model_primary
                )
            case LLMProvider.BEDROCK:
                return self._settings.bedrock_model_primary
            case LLMProvider.OPENAI:
                return self._settings.openai_model_primary
            case LLMProvider.MARITACA:
                return self._settings.maritaca_model
            case LLMProvider.VLLM:
                return self._settings.vllm_model
            case _:
                raise ValueError(f"Unknown provider: {provider}")
