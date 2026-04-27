# FHIR-Forge — Guia Claude Code

Pipeline híbrido (LLM + SUSHI + validators) que converte especificações de API (OpenAPI/Swagger) em recursos FHIR R4 conformes ao **BR Core** e à **RNDS** (Registro Nacional de Dados em Saúde).

```
OpenAPI spec
    └─► SwaggerLens (parse) ──► FhirForge (LLM map) ──► HAPI $validate ──► Bundle RNDS
                                        │
                               TermMapper (SNOMED/LOINC/CID-10)
```

---

## §1 — Visão Geral

| Item | Detalhe |
|------|---------|
| Nome | fhir-forge |
| Versão | 0.1.0 |
| Licença | Apache-2.0 |
| Autor | Cassiano Moralles |
| Python | ≥ 3.12 |
| FHIR | R4 + BR Core 1.0.0 |
| RNDS | Homologação + Produção |
| Status | 9/9 fases completas — todos os gates verdes |
| Testes | 252 unit, 91% cobertura, ruff + mypy strict OK |

**LLM routing** (em ordem de prioridade):

1. `claude-opus-4-7` via Anthropic (padrão, dados não-PHI)
2. `claude-haiku-4-5-20251001` via Anthropic (tarefas rápidas)
3. `anthropic.claude-sonnet-4-6-v1:0` via AWS Bedrock (fallback cloud)
4. `sabia-4` via Maritaca (PT-BR nativo)
5. `meta-llama/Llama-3.3-70B-Instruct` via vLLM on-prem (`FEATURE_ALLOW_PHI_EGRESS=false`)

---

## §2 — Estrutura de Diretórios

```
fhir-forge/
├── apps/
│   ├── api/              # FastAPI gateway (porta 8000)
│   └── worker/           # Dramatiq workers (conversão async)
├── packages/
│   ├── core/             # Settings, tipos base, logging, llm_router
│   ├── swagger_lens/     # Parser OpenAPI 2.0/3.x → SwaggerSpec tipado
│   ├── fhir_forge/       # LangGraph agent: SwaggerSpec → FhirBundle
│   ├── term_mapper/      # Lookup terminológico (SNOMED, LOINC, CID-10, TUSS)
│   ├── connectors/       # HAPI client + RNDS client (mTLS) + resiliência
│   ├── eval/             # Pipeline de avaliação de qualidade
│   └── mcp_server/       # Servidor MCP (fastmcp) com tools FHIR
├── data/
│   ├── snomed-import/    # RF2 release para carga no Snowstorm
│   ├── codesystems/      # CID-10, TUSS, SIGTAP, LOINC, SNOMED dumps
│   ├── conceptmaps/      # ConceptMaps exportados do HAPI
│   └── golden/
│       ├── swagger_specs/   # Specs OpenAPI de referência
│       ├── fhir_bundles/    # Bundles FHIR esperados (regression)
│       └── conceptmap_pairs/ # Pares de mapeamento para eval
├── ig/
│   ├── input/fsh/        # FSH sources (SUSHI)
│   └── output/           # HTML gerado pelo IG Publisher
├── tests/
│   ├── conftest.py       # Fixtures session-scoped (testcontainers)
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── e2e/
├── secrets/              # Certs RNDS (.pfx) — nunca commitar
├── tools/                # validator_cli.jar
├── scripts/
│   ├── bootstrap.sh
│   ├── postgres-init.sh
│   ├── generate_pptx.py    # gera apresentação PPTX (arquitetos)
│   └── generate_docx.py    # gera documento DOCX (arquitetos)
├── docker-compose.yml
├── pyproject.toml
├── Makefile
└── .env.example
```

---

## §3 — Princípios de Design

### FHIR-first
Todo dado sai validado. Use `POST /fhir/[Type]/$validate` no HAPI ou `validator_cli.jar` para validação local. Nunca retorne um recurso sem validação.

### Async-first
Toda função que faz I/O externo (HTTP, DB, queue) usa `async def`. Use `httpx.AsyncClient` — nunca `requests`. Workers Dramatiq são síncronos (limitação do framework); use `asyncio.run()` quando necessário dentro de actors.

### PHI-safety
`FEATURE_ALLOW_PHI_EGRESS=false` por padrão. O `llm_router` em `packages/core` verifica esse flag antes de enviar dados para LLMs cloud. Dados com PHI **sempre** vão para o vLLM on-prem.

### Observability-by-default
- Todo LLM call: `langfuse.trace()` com input/output
- Todo endpoint FastAPI: OTEL span automático via `opentelemetry-instrumentation-fastapi`
- Todo log: `structlog` com contexto de request (request_id, user_id, resource_type)
- Nunca usar `print()` ou `logging.basicConfig()` diretamente

### Fail-fast, recover-gracefully
- `tenacity` para retry em chamadas externas (HAPI, Snowstorm, RNDS)
- `pybreaker` para circuit breaker em `packages/connectors`
- Dramatiq DLQ após 3 falhas; não perder tarefas silenciosamente

---

## §4 — Padrões Python

### Ferramentas
```bash
uv sync --all-extras --dev   # instalar deps
uv run ruff check .          # lint
uv run ruff format .         # format
uv run mypy packages apps    # type check
uv run pytest -m unit        # testes unit
```

### Workspace members
Cada package/app em `packages/` e `apps/` é um membro do uv workspace com seu próprio `pyproject.toml`:

```toml
[project]
name = "fhir-forge-<nome>"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fhir-forge-core"]  # dependência interna

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### Tipagem
- Todos os módulos com `from __future__ import annotations`
- `TypedDict` para estados LangGraph
- `Protocol` para interfaces entre packages
- `dataclass` ou Pydantic `BaseModel` para DTOs — sem dicts soltos
- Proibido: `Any`, `# type: ignore` sem comentário explicativo

### Settings por package
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    hapi_base_url: str = "http://localhost:8090/fhir"

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
```

### Logging
```python
import structlog

log = structlog.get_logger(__name__)

async def process(job_id: str) -> None:
    log.info("processing_job", job_id=job_id)
```

### Imports
- Absolutos entre packages: `from core.settings import settings`
- Relativos dentro do mesmo package: `from .mapper import map_resource`
- Isort via ruff (grupo: stdlib → third-party → first-party → local)

---

## §5 — FHIR & BR Core

### Recursos principais usados
`Patient`, `Practitioner`, `Organization`, `Encounter`, `Observation`, `Condition`, `MedicationRequest`, `DiagnosticReport`, `Bundle`

### Modelagem Python
```python
from fhir.resources.patient import Patient
from fhir.resources.bundle import Bundle, BundleEntry

patient = Patient(
    id="p1",
    name=[{"use": "official", "family": "Silva", "given": ["João"]}],
)
```

### Validação local (sem Docker)
```bash
make validate FILE=examples/patient.json
# equivale a:
java -jar tools/validator_cli.jar examples/patient.json \
    -version 4.0.1 -ig br.gov.saude.br-core.fhir#1.0.0
```

### Validação online (HAPI)
```python
import httpx

async def validate_resource(resource: dict, profile: str | None = None) -> dict:
    url = f"{settings.hapi_base_url}/{resource['resourceType']}/$validate"
    params = {"profile": profile} if profile else {}
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=resource, params=params)
    return r.json()  # OperationOutcome
```

### BR Core no HAPI
Para ativar, descomente no `docker-compose.yml`:
```yaml
hapi.fhir.implementationguides.brcore.name: br.gov.saude.br-core.fhir
hapi.fhir.implementationguides.brcore.version: 1.0.0
hapi.fhir.implementationguides.brcore.installMode: STORE_AND_INSTALL
```
Depois: `docker compose restart hapi`

### Golden pairs (regression)
Todo par `(swagger_spec, fhir_bundle)` bem-sucedido vira fixture:
```
data/golden/swagger_specs/api_xyz_v2.yaml
data/golden/fhir_bundles/api_xyz_v2_expected.json
```

---

## §6 — LangGraph & LLM

### Estrutura do grafo (fhir_forge)
```python
from langgraph.graph import StateGraph
from typing import TypedDict

class ConversionState(TypedDict):
    swagger_spec: SwaggerSpec
    fhir_resources: list[dict]
    validation_result: ValidationResult | None
    errors: list[str]

graph = StateGraph(ConversionState)
graph.add_node("parse_endpoints", parse_endpoints_node)
graph.add_node("map_resources", map_resources_node)
graph.add_node("validate", validate_node)
graph.add_node("fix_errors", fix_errors_node)
graph.add_edge("parse_endpoints", "map_resources")
graph.add_conditional_edges("validate", route_on_validation)
```

### Checkpoints (LangGraph + Postgres)
```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(settings.langgraph_db_url) as saver:
    compiled = graph.compile(checkpointer=saver)
```

### Tracing LLM (Langfuse)
```python
from langfuse import Langfuse

langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host,
)

with langfuse.trace(name="fhir_conversion", input=swagger_spec.dict()) as trace:
    result = await compiled.ainvoke(state, config={"thread_id": job_id})
    trace.update(output=result)
```

---

## §7 — Async & Queue (Dramatiq)

### Configuração do broker
```python
import dramatiq
from dramatiq.brokers.redis import RedisBroker

broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(broker)
```

### Actor padrão
```python
@dramatiq.actor(queue_name="fhir", max_retries=3, time_limit=300_000)
def convert_spec_actor(job_id: str, swagger_yaml: str) -> None:
    # Verificar idempotência
    if job_exists(job_id):
        return
    asyncio.run(_convert(job_id, swagger_yaml))
```

### Filas
- `default` — tarefas genéricas
- `fhir` — conversões (priority)
- `fhir_dlq` — dead letter após max_retries

---

## §8 — Estratégia de Testes

### Camadas

| Camada | Marker | Velocidade | O que testa |
|--------|--------|-----------|-------------|
| Unit | `unit` | < 1 s | Lógica pura; mocks via `respx` e `unittest.mock` |
| Integration | `integration` | 5–30 s | Testcontainers: Postgres + Redis + HAPI real |
| Regression | `regression` | 5–15 s | Golden-file diff semântico; output FHIR não regride |
| E2E | `e2e` | 30–120 s | Stack Docker completa; saga OpenAPI → Bundle |
| RNDS | `rnds` | variável | Sandbox RNDS; só com credenciais em env |

### Cobertura mínima por fase (gate obrigatório)
- `packages/core`, `packages/swagger_lens`, `packages/term_mapper`, `packages/connectors`: **≥ 80%**
- `packages/fhir_forge`: **≥ 75%** (LLM paths difíceis de cobrir sem mocks excessivos)
- `packages/eval`, `packages/mcp_server`: **≥ 70%**
- `apps/api`, `apps/worker`: **≥ 70%**

### Unit tests — regras
- Um arquivo `tests/unit/test_<module>.py` por módulo
- Sem I/O real (banco, HTTP, filesystem)
- Mock HTTP com `respx.mock` context manager
- Mock LLM: fixture `mock_anthropic` que retorna resposta canned
- Property-based: `hypothesis` para parsers de entrada variável

### Integration tests — regras
- Fixtures em `tests/conftest.py` com `scope="session"` para containers
- `PostgresContainer` + `RedisContainer` + container HAPI customizado
- Nunca mockar banco ou HAPI nesta camada
- Usar dados sintéticos — nunca dados de pacientes reais

### Regression tests — regras
- `tests/regression/test_golden.py`: itera `data/golden/` e compara output
- Diff semântico com `deepdiff` (ignora `id`, `meta.lastUpdated`, `meta.versionId`)
- Falha em regressão = bloqueador de merge
- Para aceitar mudança intencional: `make golden-update FILE=<nome>` (a implementar no Makefile)

### CI (futuro — GitHub Actions)
```
push  → unit + lint + mypy     (< 3 min)
PR    → unit + integration + regression  (< 12 min)
main  → tudo (incluindo e2e)   (< 20 min)
```

---

## §9 — Infraestrutura

### Serviços locais

| Serviço | URL | Uso |
|---------|-----|-----|
| HAPI FHIR | http://localhost:8090/fhir | $validate, $expand, CRUD |
| Snowstorm | http://localhost:8080/fhir | SNOMED CT terminology |
| Postgres | localhost:5432 | HAPI JPA, LangGraph, app data |
| Redis | localhost:6379 | Dramatiq queue, cache |
| MinIO | http://localhost:9000 | Artefatos S3-compatible |
| Langfuse | http://localhost:3000 | LLM traces |

### Makefile (principais targets)
```bash
make bootstrap       # setup único
make up              # sobe stack
make health          # checa todos os serviços
make test            # pytest unit
make test-int        # pytest integration
make test-all        # tudo
make lint            # ruff + mypy
make fmt             # ruff format + fix
make validate FILE=  # valida FHIR contra BR Core
make api             # sobe FastAPI dev
make worker          # sobe Dramatiq worker
make db-migrate      # Alembic upgrade head
make docs            # gera PPTX + DOCX em docs/
```

### Feature flags (.env)
| Flag | Default | Uso |
|------|---------|-----|
| `FEATURE_ALLOW_PHI_EGRESS` | `false` | Permite PHI em LLMs cloud |
| `FEATURE_ADMIN_NOAUTH` | `true` | Endpoints admin sem auth (só dev) |
| `FEATURE_MCP_ENABLED` | `true` | MCP server em /mcp |

---

## §10 — Prompts de Implementação por Fase

> Referência histórica dos prompts de implementação usados em cada fase. Todas as 9 fases foram concluídas. Use como documentação de intenção de design.

---

### §10.1 — Fase 1: `packages/core`

**Pré-requisito**: Gate 0 verde (`make health` OK).

```
Implemente packages/core — o package de infraestrutura compartilhada do fhir-forge.

Contexto: Este é um uv workspace. O package deve ficar em packages/core/
com src layout (packages/core/src/core/). Veja pyproject.toml na raiz para
padrões de ruff, mypy (strict) e pytest.

Crie os seguintes módulos:

1. packages/core/pyproject.toml
   - name: "fhir-forge-core"
   - sem dependências internas (é a base)
   - deps: pydantic-settings, structlog, httpx, anthropic, langfuse, opentelemetry-*

2. packages/core/src/core/settings.py
   - Classe Settings (pydantic-settings) com TODOS os campos do .env.example
   - Campos tipados: hapi_base_url: str, anthropic_api_key: SecretStr, etc.
   - feature_allow_phi_egress: bool = False
   - feature_mcp_enabled: bool = True

3. packages/core/src/core/logging.py
   - configure_logging(level: str, fmt: str) → None
   - Usa structlog com ProcessorFormatter
   - JSON em produção, console colorido em dev
   - Adiciona request_id ao contexto via contextvars

4. packages/core/src/core/types.py
   - ResourceType: StrEnum com valores FHIR R4 comuns (Patient, Observation, etc.)
   - ConversionJob: dataclass com id (ULID), status, created_at
   - ValidationResult: dataclass com valid: bool, issues: list[Issue]
   - Issue: dataclass com severity, code, details

5. packages/core/src/core/exceptions.py
   - FhirForgeError (base)
   - ValidationError, MappingError, TerminologyError, ConnectorError

6. packages/core/src/core/llm_router.py
   - LLMRouter com método get_client(phi_data: bool) → AsyncAnthropic | ...
   - Respeita FEATURE_ALLOW_PHI_EGRESS: se false, phi_data=True → vLLM
   - Routing: anthropic → bedrock → vllm por disponibilidade

Testes obrigatórios:
- tests/unit/test_settings.py — valida defaults, override por env var
- tests/unit/test_llm_router.py — routing PHI=True com egress=False vai vLLM
- tests/unit/test_types.py — serialização ConversionJob, ValidationResult

Gate 1 de saída:
- make test -m unit VERDE (0 falhas)
- Cobertura packages/core ≥ 80%
- make lint VERDE (ruff + mypy strict)
- Settings instancia com .env.example sem KeyError
```

---

### §10.2 — Fase 2: `packages/swagger_lens`

**Pré-requisito**: Gate 1 verde.

```
Implemente packages/swagger_lens — parser de especificações OpenAPI/Swagger.

Contexto: Recebe YAML ou JSON (OpenAPI 2.0 ou 3.x), retorna SwaggerSpec tipado
com endpoints, schemas e metadados. Usa openapi-spec-validator e openapi-pydantic.

Módulos a criar em packages/swagger_lens/src/swagger_lens/:

1. pyproject.toml — deps: openapi-spec-validator, openapi-pydantic, PyYAML, fhir-forge-core

2. models.py
   - SwaggerSpec: dataclass com title, version, base_url, endpoints: list[Endpoint]
   - Endpoint: dataclass com path, method, operation_id, summary, params, request_body, responses
   - SchemaRef: Union[dict, str] (resolve $ref)

3. parser.py
   - parse_spec(content: str | bytes, fmt: Literal["yaml","json","auto"]) → SwaggerSpec
   - Suporte OpenAPI 2.0 (swagger) e 3.0/3.1
   - Valida contra spec antes de parsear (openapi-spec-validator)
   - Lança FhirForgeError se spec inválida

4. flattener.py
   - flatten_schema(schema: dict, spec: dict) → dict
   - Resolve $ref recursivamente (evita loops: set de refs visitadas)
   - Expande allOf, oneOf, anyOf

5. extractor.py
   - extract_fhir_hints(endpoint: Endpoint) → list[str]
   - Infere tipos FHIR prováveis a partir de nomes de campos, tags, operationId

Testes obrigatórios:
- tests/unit/test_parser.py
  - Parseia spec OpenAPI 2.0 e 3.0 hardcoded
  - hypothesis: SpecStrategy gera specs mínimas válidas; parser não lança exceção
  - Spec inválida → FhirForgeError
- tests/unit/test_flattener.py
  - $ref simples, $ref circular (deve detectar e não loop infinito)
  - allOf, oneOf com discriminator
- tests/integration/test_swagger_lens_golden.py
  - Lê todos os arquivos em data/golden/swagger_specs/ e parseia sem erro
  - (Crie pelo menos 1 spec de exemplo em data/golden/swagger_specs/example_api.yaml)

Gate 2 de saída:
- make test -m unit VERDE
- make test -m integration VERDE (para swagger_lens)
- Cobertura ≥ 80%
- make lint VERDE
- hypothesis não falsifica após 200 exemplos
```

---

### §10.3 — Fase 3: `packages/fhir_forge`

**Pré-requisito**: Gate 2 verde.

```
Implemente packages/fhir_forge — o agente LangGraph que converte SwaggerSpec em FhirBundle.

Este é o package central do produto. Usa LangGraph com checkpoints Postgres,
prompts Anthropic, e valida o resultado no HAPI.

Módulos em packages/fhir_forge/src/fhir_forge/:

1. pyproject.toml — deps: langgraph, langgraph-checkpoint-postgres, anthropic,
   fhir.resources, fhir-forge-core, fhir-forge-swagger-lens, fhir-forge-connectors

2. state.py
   - ConversionState (TypedDict): swagger_spec, endpoints_to_process, fhir_resources,
     validation_errors, retry_count, job_id, trace_id

3. nodes/
   - parse_node.py: extrai endpoints prioritários do SwaggerSpec
   - mapping_node.py: chama LLM (via llm_router) para mapear endpoint → FHIR resource
     Prompt: few-shot com exemplos BR Core; output structured (JSON mode)
   - validation_node.py: POST $validate no HAPI para cada resource
   - fix_node.py: chama LLM com erros de validação para corrigir resource
   - bundle_node.py: monta Bundle FHIR R4 com todos os resources válidos

4. graph.py
   - Monta StateGraph com os 5 nós
   - conditional_edge em validation_node: VALID → bundle, INVALID (retry<3) → fix, INVALID (retry≥3) → bundle com warnings
   - Compila com AsyncPostgresSaver

5. service.py
   - async convert(swagger_spec: SwaggerSpec, job_id: str) → Bundle
   - Rastreia toda conversão no Langfuse

Testes obrigatórios:
- tests/unit/test_mapping_node.py
  - Mock Anthropic (respx), verifica que output é dict FHIR válido
  - Mock com resposta malformada → FhirForgeError
- tests/unit/test_graph_transitions.py
  - Simula state válido → bundle_node chamado
  - Simula state inválido retry<3 → fix_node chamado
  - Simula state inválido retry≥3 → bundle_node com warnings
- tests/integration/test_fhir_forge_integration.py
  - HAPI testcontainer; convert() retorna Bundle sem erros de validação
  - Bundle tem ao menos 1 entry
- tests/regression/test_golden_bundles.py
  - Para cada par em data/golden/: converte e compara com deepdiff
  - Ignora campos: id, meta.lastUpdated, meta.versionId

Gate 3 de saída (MAIS RESTRITO):
- 2 pares golden passam regressão (diff semântico zero)
- $validate HAPI retorna 0 erros para todos os bundles gerados
- Traces visíveis no Langfuse (smoke manual)
- Cobertura ≥ 75%
- make lint VERDE
```

---

### §10.4 — Fase 4: `packages/term_mapper`

**Pré-requisito**: Gate 3 verde.

```
Implemente packages/term_mapper — lookup terminológico com cache Redis.

Suporta: SNOMED CT (via Snowstorm), LOINC, CID-10, TUSS, SIGTAP.
Cache Redis com TTL configurável.

Módulos em packages/term_mapper/src/term_mapper/:

1. pyproject.toml — deps: redis, httpx, fhir-forge-core

2. models.py
   - Coding: dataclass com system, code, display
   - ConceptMatch: dataclass com coding, score: float, source: str

3. cache.py
   - TermCache usando Redis
   - get(system, code) → Coding | None
   - set(system, code, coding, ttl=3600)
   - Serialização JSON

4. snowstorm_client.py
   - async find_concept(term: str, ecl: str | None) → list[ConceptMatch]
   - async translate(system: str, code: str, target: str) → Coding | None
   - Base URL: settings.snowstorm_base_url + "/fhir"

5. hapi_valueset_client.py
   - async expand(valueset_url: str, filter: str | None) → list[Coding]
   - async lookup(system: str, code: str) → Coding | None
   - Usa HAPI $expand e $lookup operations

6. mapper.py
   - TermMapper: orquestra cache → Snowstorm → HAPI fallback
   - async map_code(system: str, code: str, preferred_system: str) → Coding | None

Testes obrigatórios:
- tests/unit/test_cache.py — hit não faz HTTP; miss chama Snowstorm; TTL expirado re-fetcha
- tests/unit/test_snowstorm_client.py — respx mock, 200 e 404
- tests/unit/test_mapper.py — cache hit, cache miss + Snowstorm, Snowstorm 404 + HAPI fallback
- tests/integration/test_term_integration.py
  - HAPI testcontainer com ValueSet pré-carregado (fixture: POST ValueSet antes dos testes)
  - expand() retorna lista correta

Gate 4 de saída:
- 10 lookups corretos (unit com mock)
- Cache hit não gera HTTP (unit)
- $expand funciona no HAPI de integração
- Cobertura ≥ 80%
- make lint VERDE
```

---

### §10.5 — Fase 5: `packages/connectors`

**Pré-requisito**: Gate 4 verde.

```
Implemente packages/connectors — clientes HTTP resilientes para HAPI e RNDS.

Módulos em packages/connectors/src/connectors/:

1. pyproject.toml — deps: httpx, tenacity, pybreaker, fhir-forge-core

2. hapi_client.py
   HapiFhirClient:
   - create(resource: dict) → dict
   - read(resource_type: str, resource_id: str) → dict
   - update(resource: dict) → dict
   - delete(resource_type: str, resource_id: str) → None
   - search(resource_type: str, params: dict) → list[dict]  (paginação automática)
   - validate(resource: dict, profile: str | None) → ValidationResult
   - Retry: tenacity, 3 tentativas, exponential backoff
   - Circuit breaker: pybreaker, threshold=5 falhas em 60s

3. rnds_client.py
   RndsClient:
   - Autenticação mTLS (pfx via RNDS_CERT_PATH)
   - async get_token() → str  (cache token até expirar)
   - async submit_document(document: dict) → str  (retorna protocolo)
   - async get_document(protocol_id: str) → dict
   - Base URL: settings.rnds_base_url

4. resilience.py
   - retry_async: decorator tenacity para funções async
   - fhir_circuit_breaker: pybreaker.CircuitBreaker pré-configurado

Testes obrigatórios:
- tests/unit/test_hapi_client.py — respx mock; CRUD, busca paginada, 404 → None
- tests/unit/test_rnds_client.py — mock cert load, mock token, mock submit
- tests/unit/test_resilience.py
  - retry: falha 2x depois sucesso → chamado 3x total
  - circuit breaker: abre após 5 falhas, lança OpenError
  - circuit breaker: fecha após cooldown (mock time)
- tests/integration/test_hapi_client_integration.py
  - HAPI testcontainer; create → read → update → search → delete (CRUD completo)
- tests/rnds/test_rnds_sandbox.py (marker rnds)
  - Só roda com RNDS_CERT_PATH presente no env

Gate 5 de saída:
- CRUD HAPI testado (unit + integration)
- Circuit breaker abre/fecha testado (unit)
- Cobertura ≥ 80%
- make lint VERDE
- tests rnds marcados (não bloqueiam CI sem credencial)
```

---

### §10.6 — Fase 6: `apps/api`

**Pré-requisito**: Gate 5 verde.

```
Implemente apps/api — FastAPI gateway do fhir-forge.

Estrutura em apps/api/src/api/:

1. pyproject.toml — deps: fastapi, uvicorn[standard], fhir-forge-core,
   fhir-forge-fhir-forge, fhir-forge-connectors, opentelemetry-instrumentation-fastapi

2. main.py
   - FastAPI app com lifespan (startup: configure_logging, init OTEL)
   - Inclui todos os routers
   - OTEL: FastAPIInstrumentor().instrument_app(app)
   - Middleware: request_id em cada request (contextvars)

3. routers/
   health.py:
   - GET /health → {"status": "ok", "services": {...}}
   - Checa HAPI, Redis, Postgres

   convert.py:
   - POST /convert (body: {"spec": <yaml_string>, "options": {}}) → Job
   - Enfileira no Dramatiq se async=true, executa inline se async=false
   - Retorna job_id, status, bundle (se síncrono)

   fhir.py:
   - GET /fhir/{resource_type}/{id} — proxy para HAPI
   - POST /fhir/{resource_type}/$validate — proxy para HAPI validate

   mcp.py:
   - Monta o MCP server do packages/mcp_server em /mcp (se FEATURE_MCP_ENABLED)

4. schemas.py — Pydantic models de request/response da API (não confundir com FHIR)

5. auth.py
   - Bearer token middleware (simples para dev)
   - FEATURE_ADMIN_NOAUTH=true → bypass em dev

Testes obrigatórios:
- tests/unit/test_routers_health.py — mock services, GET /health 200
- tests/unit/test_routers_convert.py — mock fhir_forge.service, POST /convert síncrono
- tests/unit/test_auth.py — bearer ok, bearer inválido 401, ADMIN_NOAUTH bypass
- tests/integration/test_api_integration.py
  - HAPI + Postgres testcontainers
  - POST /convert com spec real → 200 com bundle
- tests/e2e/test_api_e2e.py (marker e2e)
  - make api rodando; curl /health; POST /convert end-to-end

Gate 6 de saída:
- GET /health → 200 {"status": "ok"}
- POST /convert → bundle FHIR válido
- GET /openapi.json → sem erros de schema
- Cobertura apps/api ≥ 70%
- make lint VERDE
```

---

### §10.7 — Fase 7: `apps/worker`

**Pré-requisito**: Gate 6 verde.

```
Implemente apps/worker — Dramatiq workers para conversão assíncrona.

Estrutura em apps/worker/:

1. pyproject.toml — deps: dramatiq[redis,watch], fhir-forge-core, fhir-forge-fhir-forge

2. main.py — configura broker Redis; importa todos os actors

3. actors/
   conversion.py:
   - convert_spec_actor(job_id: str, swagger_yaml: str) → None
   - Verifica idempotência por job_id (Redis SET NX)
   - Chama fhir_forge.service.convert()
   - Salva resultado no Postgres / MinIO
   - Em falha → propaga (Dramatiq faz retry automático)

4. dlq_handler.py
   - Actor na fila fhir_dlq para tratar mensagens mortas
   - Loga, notifica (Langfuse), salva status FAILED

Testes obrigatórios:
- tests/unit/test_conversion_actor.py
  - Mock fhir_forge.service; actor chama convert() com args corretos
  - job_id duplicado: convert() não chamado segunda vez (idempotência)
- tests/unit/test_dlq_handler.py — mensagem morta salva status FAILED
- tests/integration/test_queue_integration.py
  - Redis testcontainer; enqueue → consume → assert resultado no Postgres

Gate 7 de saída:
- Actor processa tarefa corretamente (unit)
- Idempotência: tarefa duplicada ignorada (unit)
- DLQ recebe após 3 falhas (unit)
- Cobertura ≥ 75%
- make lint VERDE
```

---

### §10.8 — Fase 8: `packages/eval`

**Pré-requisito**: Gate 7 verde.

```
Implemente packages/eval — pipeline de avaliação de qualidade das conversões.

Métricas principais:
- precision/recall de mapeamentos FHIR (comparando com golden)
- taxa de validação BR Core ($validate sem erros)
- latência média de conversão (p50, p95)
- cobertura terminológica (% de códigos mapeados com sucesso)

Módulos em packages/eval/src/eval/:

1. pyproject.toml — deps: fhir-forge-core, fhir-forge-fhir-forge, deepdiff, rich

2. metrics.py
   - fhir_precision(predicted: dict, expected: dict) → float
   - fhir_recall(predicted: dict, expected: dict) → float
   - semantic_diff(a: dict, b: dict, ignore_paths: list[str]) → dict
   - Usa deepdiff com ignorar: id, meta.lastUpdated, meta.versionId

3. runner.py
   - EvalRunner.run(golden_dir: Path) → EvalReport
   - Para cada par em golden_dir: converte + compara + valida
   - Retorna EvalReport com métricas agregadas

4. report.py
   - EvalReport: dataclass com métricas, timestamp, pairs testados
   - to_json() → str
   - print_summary(console: Console) → None  (usa rich)

Testes obrigatórios:
- tests/unit/test_metrics.py — precision/recall com bundles sintéticos
- tests/regression/test_eval_regression.py
  - Carrega baseline de eval (JSON fixado)
  - Métricas atuais não devem regredir > 5% vs baseline
  - Se não existe baseline, gera e avisa

Gate 8 de saída:
- Relatório gerado para ≥ 2 pares golden (pode ser mock se golden vazio)
- Precision ≥ 0.8 no dataset de referência
- Cobertura ≥ 70%
- make lint VERDE
```

---

### §10.9 — Fase 9: `packages/mcp_server`

**Pré-requisito**: Gate 1 verde (só depende de core).

```
Implemente packages/mcp_server — servidor MCP com ferramentas FHIR para Claude.

O servidor usa fastmcp e expõe 6 tools para que Claude interaja com a stack FHIR
em tempo de execução (validar resources, buscar conceitos SNOMED, etc.).

Estrutura em packages/mcp_server/src/mcp_server/:

1. pyproject.toml — deps: fastmcp>=3.0, httpx, fhir-forge-core

2. settings.py
   class McpSettings(BaseSettings):
       hapi_base_url: str = "http://localhost:8090/fhir"
       snowstorm_base_url: str = "http://localhost:8080"
       mcp_host: str = "localhost"
       mcp_port: int = 8001

3. tools/hapi.py — 4 tools decorados com @mcp.tool():
   - validate_resource(resource_json: str, profile_url: str | None = None) → dict
     POST $validate, retorna {"valid": bool, "issues": [...]}
   - get_resource(resource_type: str, resource_id: str) → dict
     GET /fhir/{type}/{id}
   - search_resources(resource_type: str, params: str) → list[dict]
     GET /fhir/{type}?params (params como query string "key=val&key2=val2")
   - expand_valueset(valueset_url: str, filter: str | None = None) → list[dict]
     GET /fhir/ValueSet/$expand?url=...&filter=...

4. tools/snowstorm.py — 2 tools:
   - find_concept(term: str, ecl_filter: str | None = None) → list[dict]
     GET /fhir/CodeSystem/$lookup ou /browser/MAIN/concepts?term=...
   - translate_code(source_system: str, source_code: str, target_system: str) → dict | None
     POST /fhir/ConceptMap/$translate

5. server.py
   mcp = FastMCP("fhir-forge")
   # Registra todos os tools de hapi.py e snowstorm.py
   # Transport: streamable-http em mcp_settings.mcp_host:mcp_port/mcp

Testes obrigatórios:
- tests/unit/test_hapi_tools.py — respx mock para cada um dos 4 tools
- tests/unit/test_snowstorm_tools.py — respx mock para 2 tools
- tests/integration/test_mcp_integration.py
  - HAPI testcontainer; validate_resource com recurso válido → {"valid": true}
  - validate_resource com recurso inválido → {"valid": false, "issues": [...]}

Gate 9 de saída:
- uv run python -c "from mcp_server.server import mcp" sem ImportError
- validate_resource retorna resultado real do HAPI (integration)
- Cobertura ≥ 70%
- make lint VERDE
```

---

## Checklist de Gates

| Gate | Fase | Critério principal |
|------|------|--------------------|
| 0 | Bootstrap | `make health` todos OK |
| 1 | core | unit verde, cobertura ≥ 80%, mypy strict |
| 2 | swagger_lens | parseia 5 specs, hypothesis 200 exemplos |
| 3 | fhir_forge | 2 golden pairs sem regressão, $validate 0 erros |
| 4 | term_mapper | 10 lookups corretos, cache Redis testado |
| 5 | connectors | CRUD HAPI integration, circuit breaker testado |
| 6 | api | /health 200, /convert funcional, openapi.json OK |
| 7 | worker | actor processa, idempotência, DLQ funcional |
| 8 | eval | relatório gerado, precision ≥ 0.8 |
| 9 | mcp_server | import sem erro, validate_resource HAPI real |

---

## §11 — Status Final (Abril 2026)

Todas as 9 fases do pipeline estão implementadas e com gates verdes.

| Fase | Package/App | Status |
|------|-------------|--------|
| 1 | `packages/core` | Completo — Settings, LLMRouter, types, exceptions, logging |
| 2 | `packages/swagger_lens` | Completo — parser OpenAPI 2.0/3.x, flattener, extractor |
| 3 | `packages/fhir_forge` | Completo — LangGraph 5 nós, checkpointer Postgres |
| 4 | `packages/term_mapper` | Completo — SNOMED/LOINC/CID-10/TUSS, Redis cache |
| 5 | `packages/connectors` | Completo — HAPI client (tenacity), RNDS client (mTLS) |
| 6 | `apps/api` | Completo — FastAPI gateway, 4 routers, OTEL |
| 7 | `apps/worker` | Completo — Dramatiq actors, DLQ handler, idempotência Redis |
| 8 | `packages/eval` | Completo — precision/recall, EvalRunner, relatório rich |
| 9 | `packages/mcp_server` | Completo — 6 FastMCP tools (4 HAPI + 2 Snowstorm) |

**Métricas do projeto:**

- 252 testes unitários passando (< 1s cada)
- Cobertura: 91% global
- Lint (ruff check): 0 erros
- Type check (mypy strict): 0 erros

**Para gerar documentação de arquitetura:**

```bash
uv sync --dev                            # instala python-pptx e python-docx
uv run python scripts/generate_pptx.py  # → docs/fhir-forge-arquitetura.pptx
uv run python scripts/generate_docx.py  # → docs/fhir-forge-arquitetura.docx
```
