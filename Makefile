# FHIR-Forge — Makefile
# Atalhos para tarefas frequentes. Documentar cada alvo no help.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ─── Cores ────────────────────────────────────────────────────
BLUE := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RESET := \033[0m

# ─── Variáveis ────────────────────────────────────────────────
COMPOSE := docker compose
UV := uv
PYTHON := uv run python

# ═════════════════════════════════════════════════════════════
# HELP
# ═════════════════════════════════════════════════════════════
.PHONY: help
help: ## Mostra esta ajuda
	@echo ""
	@echo "$(BLUE)FHIR-Forge — comandos disponíveis$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-22s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ═════════════════════════════════════════════════════════════
# BOOTSTRAP — primeira execução
# ═════════════════════════════════════════════════════════════
.PHONY: bootstrap
bootstrap: ## Setup completo de zero (uma vez por máquina)
	@bash scripts/bootstrap.sh

.PHONY: env
env: ## Cria .env a partir de .env.example se ausente
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(GREEN)✓$(RESET) .env criado a partir de .env.example"; \
		echo "$(YELLOW)→ edite as variáveis sensíveis antes de rodar$(RESET)"; \
	else \
		echo ".env já existe"; \
	fi

.PHONY: secrets
secrets: ## Gera segredos aleatórios para Langfuse e cola na clipboard
	@echo "LANGFUSE_NEXTAUTH_SECRET=$$(openssl rand -base64 32)"
	@echo "LANGFUSE_SALT=$$(openssl rand -base64 32)"
	@echo "LANGFUSE_ENCRYPTION_KEY=$$(openssl rand -hex 32)"

.PHONY: install
install: ## uv sync (instala dependências Python)
	$(UV) sync --all-extras --dev
	$(UV) run pre-commit install

# ═════════════════════════════════════════════════════════════
# DOCKER — orquestração
# ═════════════════════════════════════════════════════════════
.PHONY: up
up: env ## Sobe toda a stack (HAPI + Snowstorm + Postgres + Redis + Minio + Langfuse)
	$(COMPOSE) up -d
	@echo ""
	@echo "$(GREEN)✓ Stack subindo. Aguardando healthchecks...$(RESET)"
	@$(COMPOSE) ps

.PHONY: up-debug
up-debug: env ## Sobe stack + Adminer (UI Postgres)
	$(COMPOSE) --profile debug up -d

.PHONY: down
down: ## Derruba stack (mantém volumes)
	$(COMPOSE) down

.PHONY: nuke
nuke: ## Derruba e APAGA todos os volumes (perde dados!)
	@read -p "$(YELLOW)Tem certeza? Vai apagar volumes Postgres, ES, Minio. [y/N] $(RESET)" ans; \
	if [ "$$ans" = "y" ]; then $(COMPOSE) down -v; fi

.PHONY: ps
ps: ## Status dos serviços
	$(COMPOSE) ps

.PHONY: logs
logs: ## tail -f de todos os serviços
	$(COMPOSE) logs -f --tail=50

.PHONY: logs-hapi
logs-hapi: ## Apenas logs do HAPI
	$(COMPOSE) logs -f --tail=100 hapi

.PHONY: logs-snowstorm
logs-snowstorm: ## Apenas logs do Snowstorm + ES
	$(COMPOSE) logs -f --tail=100 snowstorm elasticsearch

.PHONY: restart
restart: ## Restart soft de todos os serviços
	$(COMPOSE) restart

# ═════════════════════════════════════════════════════════════
# HEALTH — verificações rápidas
# ═════════════════════════════════════════════════════════════
.PHONY: health
health: ## Checa endpoints de health de cada serviço
	@echo "$(BLUE)Postgres:$(RESET)     " && $(COMPOSE) exec -T postgres pg_isready -U $${POSTGRES_USER:-forge} || echo "FAIL"
	@echo "$(BLUE)Redis:$(RESET)        " && $(COMPOSE) exec -T redis redis-cli ping || echo "FAIL"
	@echo "$(BLUE)HAPI FHIR:$(RESET)    " && curl -fsS http://localhost:8090/fhir/metadata | jq -r '.software.name' 2>/dev/null || echo "FAIL"
	@echo "$(BLUE)Snowstorm:$(RESET)    " && curl -fsS http://localhost:8080/branches/MAIN | jq -r '.path' 2>/dev/null || echo "FAIL ou vazio (sem SNOMED carregado)"
	@echo "$(BLUE)Elasticsearch:$(RESET)" && curl -fsS http://localhost:9200/_cluster/health | jq -r '.status' 2>/dev/null || echo "FAIL"
	@echo "$(BLUE)Minio:$(RESET)        " && curl -fsS http://localhost:9000/minio/health/live > /dev/null && echo "ok" || echo "FAIL"
	@echo "$(BLUE)Langfuse:$(RESET)     " && curl -fsS http://localhost:3000/api/public/health > /dev/null && echo "ok" || echo "FAIL"

.PHONY: hapi-metadata
hapi-metadata: ## Mostra CapabilityStatement do HAPI
	@curl -fsS http://localhost:8090/fhir/metadata | jq '.rest[0].resource | length' | xargs -I {} echo "HAPI suporta {} resources"

# ═════════════════════════════════════════════════════════════
# DEV — ferramentas Python
# ═════════════════════════════════════════════════════════════
.PHONY: lint
lint: ## ruff check + mypy
	$(UV) run ruff check .
	$(UV) run mypy packages apps

.PHONY: fmt
fmt: ## ruff format (auto-fix)
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

.PHONY: test
test: ## Pytest unit
	$(UV) run pytest -m "unit" tests/

.PHONY: test-int
test-int: ## Pytest integration (sobe testcontainers)
	$(UV) run pytest -m "integration" tests/

.PHONY: test-all
test-all: ## Pytest tudo (lento)
	$(UV) run pytest tests/

.PHONY: cov
cov: ## Cobertura HTML
	$(UV) run pytest --cov=packages --cov-report=html tests/
	@echo "Coverage HTML em .coverage_html/index.html"

# ═════════════════════════════════════════════════════════════
# APPS — execução
# ═════════════════════════════════════════════════════════════
.PHONY: proxy
proxy: ## Sobe ProxyLLM local (porta 9099) — mock FHIR ou Ollama como backend
	$(UV) run python proxyllm/server.py

.PHONY: proxy-docker
proxy-docker: ## Sobe ProxyLLM via Docker (profile proxyllm)
	$(COMPOSE) --profile proxyllm up -d proxyllm
	@echo "$(GREEN)✓$(RESET) ProxyLLM em http://localhost:9099"

.PHONY: api
api: ## Sobe FastAPI gateway em modo dev (reload)
	$(UV) run uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: worker
worker: ## Sobe worker Dramatiq
	$(UV) run dramatiq apps.worker.main --processes 2 --threads 4

.PHONY: docs
docs: ## Gera documentação de arquitetura PPTX + DOCX em docs/
	$(PYTHON) scripts/generate_pptx.py
	$(PYTHON) scripts/generate_docx.py
	@echo "$(GREEN)✓$(RESET) Documentos gerados em docs/"

.PHONY: cli
cli: ## Atalho para CLI (ex.: make cli ARGS="lens parse url.json")
	$(UV) run forge $(ARGS)

# ═════════════════════════════════════════════════════════════
# IG / FHIR — SUSHI + IG Publisher + Validator
# ═════════════════════════════════════════════════════════════
.PHONY: sushi
sushi: ## Compila FSH com SUSHI (precisa npm install -g fsh-sushi)
	cd ig && sushi .

.PHONY: ig-build
ig-build: ## Roda IG Publisher (gera site HTML do IG)
	cd ig && ./_genonce.sh

.PHONY: ig-update-publisher
ig-update-publisher: ## Baixa última versão do IG Publisher
	cd ig && ./_updatePublisher.sh -y

.PHONY: validate
validate: ## Valida arquivo FHIR contra BR Core (uso: make validate FILE=examples/p1.json)
	@if [ -z "$(FILE)" ]; then echo "Uso: make validate FILE=path/to/resource.json"; exit 1; fi
	java -jar tools/validator_cli.jar $(FILE) -version 4.0.1 -ig br.gov.saude.br-core.fhir#1.0.0

.PHONY: download-validator
download-validator: ## Baixa HAPI validator_cli.jar para tools/
	@mkdir -p tools
	@curl -fL -o tools/validator_cli.jar https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar
	@echo "$(GREEN)✓$(RESET) validator_cli.jar baixado em tools/"

# ═════════════════════════════════════════════════════════════
# DATABASE
# ═════════════════════════════════════════════════════════════
.PHONY: db-shell
db-shell: ## Abre psql no Postgres
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-forge}

.PHONY: db-migrate
db-migrate: ## Roda migrations Alembic
	$(UV) run alembic upgrade head

.PHONY: db-revision
db-revision: ## Cria nova migration (uso: make db-revision MSG="add foo")
	$(UV) run alembic revision --autogenerate -m "$(MSG)"

# ═════════════════════════════════════════════════════════════
# CLEAN
# ═════════════════════════════════════════════════════════════
.PHONY: clean
clean: ## Limpa caches Python e build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage .coverage_html dist build *.egg-info
	rm -rf ig/output ig/input-cache
