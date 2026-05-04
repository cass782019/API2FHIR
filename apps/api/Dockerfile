FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Workspace root + lock
COPY pyproject.toml uv.lock ./

# Package pyproject.toml files (needed for workspace resolution before source copy)
COPY packages/core/pyproject.toml            packages/core/pyproject.toml
COPY packages/swagger_lens/pyproject.toml    packages/swagger_lens/pyproject.toml
COPY packages/fhir_forge/pyproject.toml      packages/fhir_forge/pyproject.toml
COPY packages/connectors/pyproject.toml      packages/connectors/pyproject.toml
COPY packages/eval/pyproject.toml            packages/eval/pyproject.toml
COPY packages/mcp_server/pyproject.toml      packages/mcp_server/pyproject.toml
COPY packages/spec_inferer/pyproject.toml    packages/spec_inferer/pyproject.toml
COPY packages/term_mapper/pyproject.toml     packages/term_mapper/pyproject.toml
COPY apps/api/pyproject.toml                 apps/api/pyproject.toml
COPY apps/worker/pyproject.toml              apps/worker/pyproject.toml
COPY apps/web/pyproject.toml                 apps/web/pyproject.toml

# Stub __init__.py so hatchling can discover workspace members during sync
RUN for pkg in \
      packages/core/src/core \
      packages/swagger_lens/src/swagger_lens \
      packages/fhir_forge/src/fhir_forge \
      packages/connectors/src/connectors \
      packages/eval/src/eval \
      packages/mcp_server/src/mcp_server \
      packages/spec_inferer/src/spec_inferer \
      packages/term_mapper/src/term_mapper \
      apps/api/src/api \
      apps/worker/src/worker; do \
        mkdir -p "$pkg" && touch "$pkg/__init__.py"; \
    done

RUN uv sync --frozen --package fhir-forge-api --no-dev

# Copy actual sources (overwrites stubs)
COPY packages/ packages/
COPY apps/api/ apps/api/

EXPOSE 8000

CMD ["uv", "run", "--package", "fhir-forge-api", \
     "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
