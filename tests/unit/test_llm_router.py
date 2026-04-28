from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr


@pytest.fixture
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.feature_allow_phi_egress = False
    s.llm_default_route = "anthropic"
    s.anthropic_model_primary = "claude-opus-4-7"
    s.anthropic_model_fast = "claude-haiku-4-5-20251001"
    s.bedrock_model_primary = "anthropic.claude-sonnet-4-6-v1:0"
    s.openai_model_primary = "gpt-4.1"
    s.maritaca_model = "sabia-4"
    s.vllm_model = "meta-llama/Llama-3.3-70B-Instruct"
    s.anthropic_api_key = SecretStr("sk-ant-test-key")
    return s


@pytest.mark.unit
def test_phi_data_true_egress_false_selects_vllm(mock_settings: MagicMock) -> None:
    from core.llm_router import LLMProvider, LLMRouter

    router = LLMRouter(mock_settings)
    assert router.selected_provider(phi_data=True) == LLMProvider.VLLM


@pytest.mark.unit
def test_phi_data_true_egress_true_selects_default_route(mock_settings: MagicMock) -> None:
    mock_settings.feature_allow_phi_egress = True
    from core.llm_router import LLMProvider, LLMRouter

    router = LLMRouter(mock_settings)
    assert router.selected_provider(phi_data=True) == LLMProvider.ANTHROPIC


@pytest.mark.unit
def test_phi_data_false_selects_anthropic(mock_settings: MagicMock) -> None:
    from core.llm_router import LLMProvider, LLMRouter

    router = LLMRouter(mock_settings)
    assert router.selected_provider(phi_data=False) == LLMProvider.ANTHROPIC


@pytest.mark.unit
def test_phi_data_false_egress_false_selects_anthropic(mock_settings: MagicMock) -> None:
    mock_settings.feature_allow_phi_egress = False
    from core.llm_router import LLMProvider, LLMRouter

    router = LLMRouter(mock_settings)
    # Non-PHI data: PHI egress flag irrelevant, uses default route
    assert router.selected_provider(phi_data=False) == LLMProvider.ANTHROPIC


@pytest.mark.unit
def test_invalid_default_route_falls_back_to_anthropic(mock_settings: MagicMock) -> None:
    mock_settings.llm_default_route = "nonexistent-provider"
    from core.llm_router import LLMProvider, LLMRouter

    router = LLMRouter(mock_settings)
    assert router.selected_provider(phi_data=False) == LLMProvider.ANTHROPIC


@pytest.mark.unit
def test_bedrock_route_selected_when_configured(mock_settings: MagicMock) -> None:
    mock_settings.llm_default_route = "bedrock"
    from core.llm_router import LLMProvider, LLMRouter

    router = LLMRouter(mock_settings)
    assert router.selected_provider(phi_data=False) == LLMProvider.BEDROCK


@pytest.mark.unit
def test_get_anthropic_client_with_valid_key(mock_settings: MagicMock) -> None:
    import anthropic
    from core.llm_router import LLMRouter

    router = LLMRouter(mock_settings)
    client = router.get_anthropic_client()
    assert isinstance(client, anthropic.AsyncAnthropic)


@pytest.mark.unit
def test_get_anthropic_client_missing_key_raises(mock_settings: MagicMock) -> None:
    mock_settings.anthropic_api_key = SecretStr("")
    from core.exceptions import ConfigurationError
    from core.llm_router import LLMRouter

    router = LLMRouter(mock_settings)
    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        router.get_anthropic_client()


@pytest.mark.unit
def test_model_id_anthropic_primary(mock_settings: MagicMock) -> None:
    from core.llm_router import LLMProvider, LLMRouter

    router = LLMRouter(mock_settings)
    assert router.model_id(LLMProvider.ANTHROPIC, fast=False) == "claude-opus-4-7"


@pytest.mark.unit
def test_model_id_anthropic_fast(mock_settings: MagicMock) -> None:
    from core.llm_router import LLMProvider, LLMRouter

    router = LLMRouter(mock_settings)
    assert router.model_id(LLMProvider.ANTHROPIC, fast=True) == "claude-haiku-4-5-20251001"


@pytest.mark.unit
def test_model_id_bedrock(mock_settings: MagicMock) -> None:
    from core.llm_router import LLMProvider, LLMRouter

    router = LLMRouter(mock_settings)
    assert router.model_id(LLMProvider.BEDROCK) == "anthropic.claude-sonnet-4-6-v1:0"


@pytest.mark.unit
def test_model_id_vllm(mock_settings: MagicMock) -> None:
    from core.llm_router import LLMProvider, LLMRouter

    router = LLMRouter(mock_settings)
    assert "Llama" in router.model_id(LLMProvider.VLLM)


@pytest.mark.unit
def test_llm_provider_enum_values() -> None:
    from core.llm_router import LLMProvider

    assert LLMProvider.ANTHROPIC == "anthropic"
    assert LLMProvider.VLLM == "vllm-onprem"
    assert LLMProvider.BEDROCK == "bedrock"
