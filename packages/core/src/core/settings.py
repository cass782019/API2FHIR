from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Postgres ──────────────────────────────────────────────────────────────
    postgres_user: str = "forge"
    postgres_password: SecretStr = SecretStr("forge_dev_change_me")
    postgres_port: int = 5432

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_port: int = 6379

    # ── MinIO ─────────────────────────────────────────────────────────────────
    minio_root_user: str = "forge"
    minio_root_password: SecretStr = SecretStr("forge_dev_change_me_min8chars")
    minio_port: int = 9000
    minio_console_port: int = 9001
    minio_bucket_artifacts: str = "forge-artifacts"
    minio_bucket_codesystems: str = "forge-codesystems"

    # ── HAPI FHIR ─────────────────────────────────────────────────────────────
    hapi_port: int = 8090
    hapi_base_url: str = "http://localhost:8090/fhir"

    # ── Snowstorm ─────────────────────────────────────────────────────────────
    snowstorm_port: int = 8080
    es_port: int = 9200

    # ── Langfuse ──────────────────────────────────────────────────────────────
    langfuse_port: int = 3000
    langfuse_nextauth_secret: SecretStr = SecretStr("")
    langfuse_salt: SecretStr = SecretStr("")
    langfuse_encryption_key: SecretStr = SecretStr("")
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: SecretStr = SecretStr("")
    langfuse_secret_key: SecretStr = SecretStr("")

    # ── Adminer ───────────────────────────────────────────────────────────────
    adminer_port: int = 8081

    # ── LLM providers ─────────────────────────────────────────────────────────
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model_primary: str = "claude-opus-4-7"
    anthropic_model_fast: str = "claude-haiku-4-5-20251001"

    aws_region: str = "us-east-1"
    aws_access_key_id: SecretStr = SecretStr("")
    aws_secret_access_key: SecretStr = SecretStr("")
    bedrock_model_primary: str = "anthropic.claude-sonnet-4-6-v1:0"

    openai_api_key: SecretStr = SecretStr("")
    openai_model_primary: str = "gpt-4.1"

    maritaca_api_key: SecretStr = SecretStr("")
    maritaca_model: str = "sabia-4"

    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_api_key: SecretStr = SecretStr("local-dev")
    vllm_model: str = "meta-llama/Llama-3.3-70B-Instruct"

    # ── LLM routing ───────────────────────────────────────────────────────────
    llm_default_route: str = "anthropic"
    llm_phi_route: str = "vllm-onprem"

    # ── Observability ─────────────────────────────────────────────────────────
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "fhir-forge"

    # ── RNDS ──────────────────────────────────────────────────────────────────
    rnds_base_url: str = "https://ehr-services.hmg.saude.gov.br"
    rnds_auth_url: str = "https://ehr-auth.hmg.saude.gov.br/api/token"
    rnds_cert_path: str = "./secrets/rnds-hml.pfx"
    rnds_cert_password: SecretStr = SecretStr("")
    rnds_cnes: str = ""
    rnds_cnpj_autorizador: str = ""
    rnds_requesting_professional_cpf: str = ""

    # ── Application ───────────────────────────────────────────────────────────
    env: str = "development"
    log_level: str = "DEBUG"
    log_format: str = "json"
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = 8000
    worker_concurrency: int = 4

    # ── Feature flags ─────────────────────────────────────────────────────────
    feature_allow_phi_egress: bool = False
    feature_admin_noauth: bool = True
    feature_mcp_enabled: bool = True

    model_config = {"env_file": ".env", "extra": "ignore", "env_file_encoding": "utf-8"}

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def postgres_dsn(self) -> str:
        """DSN for the 'forge' application database."""
        pw = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{pw}"
            f"@localhost:{self.postgres_port}/forge"
        )

    @property
    def langgraph_db_url(self) -> str:
        """DSN for the 'langgraph' checkpoints database."""
        pw = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{pw}"
            f"@localhost:{self.postgres_port}/langgraph"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://localhost:{self.redis_port}"

    @property
    def snowstorm_base_url(self) -> str:
        return f"http://localhost:{self.snowstorm_port}"


settings = Settings()
