from __future__ import annotations

import pytest


@pytest.mark.unit
def test_settings_defaults() -> None:
    from core.settings import Settings

    s = Settings()
    assert s.hapi_base_url == "http://localhost:8090/fhir"
    assert s.feature_allow_phi_egress is False
    assert s.feature_mcp_enabled is True
    assert s.postgres_port == 5432
    assert s.env == "development"
    assert s.log_level == "DEBUG"


@pytest.mark.unit
def test_settings_phi_egress_default_false() -> None:
    from core.settings import Settings

    s = Settings()
    assert s.feature_allow_phi_egress is False  # NEVER True by default


@pytest.mark.unit
def test_settings_feature_admin_noauth_default_true() -> None:
    from core.settings import Settings

    s = Settings()
    assert s.feature_admin_noauth is True  # dev convenience


@pytest.mark.unit
def test_settings_override_phi_egress_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATURE_ALLOW_PHI_EGRESS", "true")
    from core.settings import Settings

    s = Settings()
    assert s.feature_allow_phi_egress is True


@pytest.mark.unit
def test_settings_override_log_level_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    from core.settings import Settings

    s = Settings()
    assert s.log_level == "WARNING"


@pytest.mark.unit
def test_settings_override_hapi_url_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAPI_BASE_URL", "http://hapi-custom:9999/fhir")
    from core.settings import Settings

    s = Settings()
    assert s.hapi_base_url == "http://hapi-custom:9999/fhir"


@pytest.mark.unit
def test_settings_secret_fields_are_secret_str() -> None:
    from core.settings import Settings
    from pydantic import SecretStr

    s = Settings()
    assert isinstance(s.anthropic_api_key, SecretStr)
    assert isinstance(s.postgres_password, SecretStr)
    assert isinstance(s.openai_api_key, SecretStr)
    assert isinstance(s.rnds_cert_password, SecretStr)


@pytest.mark.unit
def test_settings_secret_fields_do_not_leak_in_repr() -> None:
    from core.settings import Settings

    s = Settings()
    # pydantic SecretStr masks the value in repr
    assert "forge_dev_change_me" not in repr(s.postgres_password)
    assert "**" in repr(s.postgres_password)


@pytest.mark.unit
def test_settings_computed_postgres_dsn() -> None:
    from core.settings import Settings

    s = Settings()
    dsn = s.postgres_dsn
    assert dsn.startswith("postgresql+psycopg://")
    assert "localhost" in dsn
    assert "/forge" in dsn
    assert str(s.postgres_port) in dsn


@pytest.mark.unit
def test_settings_computed_langgraph_db_url() -> None:
    from core.settings import Settings

    s = Settings()
    url = s.langgraph_db_url
    assert "/langgraph" in url
    assert url.startswith("postgresql+psycopg://")


@pytest.mark.unit
def test_settings_computed_redis_url() -> None:
    from core.settings import Settings

    s = Settings()
    assert s.redis_url.startswith("redis://")
    assert str(s.redis_port) in s.redis_url


@pytest.mark.unit
def test_settings_computed_snowstorm_base_url() -> None:
    from core.settings import Settings

    s = Settings()
    assert s.snowstorm_base_url == f"http://localhost:{s.snowstorm_port}"


@pytest.mark.unit
def test_settings_llm_defaults() -> None:
    from core.settings import Settings

    s = Settings()
    assert s.anthropic_model_primary == "claude-opus-4-7"
    assert s.anthropic_model_fast == "claude-haiku-4-5-20251001"
    assert s.llm_default_route == "anthropic"
    assert s.llm_phi_route == "vllm-onprem"


@pytest.mark.unit
def test_settings_rnds_defaults() -> None:
    from core.settings import Settings

    s = Settings()
    assert "hmg.saude.gov.br" in s.rnds_base_url
    assert s.rnds_cert_path == "./secrets/rnds-hml.pfx"


@pytest.mark.unit
def test_settings_extra_env_vars_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPLETELY_UNKNOWN_VAR_XYZ", "value")
    from core.settings import Settings

    # Should not raise ValidationError due to extra="ignore"
    s = Settings()
    assert s is not None
