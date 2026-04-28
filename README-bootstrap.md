# FHIR-Forge — Bootstrap Pack

Pacote mínimo executável para destravar a **Fase 0** do `CLAUDE.md` (§9). Coloque estes arquivos na raiz do repositório vazio, rode `make bootstrap`, e em ~10 minutos você tem stack completa rodando localmente.

**Estado atual (Abril 2026) — tag v2.1:** Todas as 9 fases completas + correções de qualidade do output FHIR. **289 unit + 3 integration + 7 regression + 6 e2e passando**, 91% de cobertura, ruff + mypy strict OK. Smoke real do `jsonAPI/schedules_1.json` (1.81 MB, 19 endpoints): 0 erros fatais e 0 warnings dom-6 no `Bundle/$validate`. Ver [CHANGELOG.md](CHANGELOG.md) para o que mudou em v2.1.

> **Versões pinadas em abril/2026**: HAPI FHIR 8.4.0-2 · Snowstorm 7.5.0 · Elasticsearch **7.17.24** · Postgres 16 (pgvector) · Redis 7.4 · Minio (release 2025-09) · Langfuse **2.x** · Adminer 4.8.1.
>
> **Nota**: ES 7.17.24 (não 8.x) — Snowstorm 7.x usa cliente Java ES 7.x. Langfuse 2.x (não 3.x) — v3 exige ClickHouse adicional.

---

## Pré-requisitos

Antes de rodar qualquer coisa, instale:

| Ferramenta | Comando de instalação |
|---|---|
| **Docker 24+** com **compose v2** | https://docs.docker.com/engine/install/ |
| **uv** (Astral) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Java 17+** (para SUSHI/IG Publisher/validator) | `sudo apt install openjdk-17-jdk` (Linux) ou `brew install openjdk@17` (macOS) |
| **Node 20+** (para SUSHI) | https://nodejs.org/ |
| **jq** (para `make health`) | `sudo apt install jq` ou `brew install jq` |
| **SUSHI** (após Node) | `npm install -g fsh-sushi` |

**RAM mínima recomendada**: 12 GB livres (Snowstorm + Elasticsearch consomem ~6 GB, HAPI ~1 GB, demais ~3 GB).

**Linux only**: Snowstorm via Elasticsearch exige `vm.max_map_count >= 262144`. Configure:

```bash
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

No Docker Desktop (macOS/Windows) isso é gerenciado automaticamente.

---

## Setup rápido

```bash
# 1. Clone o repo vazio (ou crie diretório)
mkdir fhir-forge && cd fhir-forge

# 2. Coloque os arquivos deste pacote na raiz
#    (docker-compose.yml, Makefile, pyproject.toml, .env.example, scripts/, etc.)

# 3. Bootstrap único
make bootstrap
```

O bootstrap faz:

1. Verifica pré-requisitos (Docker, uv, Java, Node, jq).
2. Confirma `vm.max_map_count` no Linux.
3. Cria `.env` a partir do `.env.example` e gera segredos do Langfuse automaticamente (openssl).
4. Cria árvore de diretórios necessária (`data/`, `ig/`, `tools/`, `secrets/`).
5. Roda `uv sync --all-extras --dev` (instala todas as deps Python).
6. Instala pre-commit hooks.
7. `docker compose pull && docker compose up -d`.
8. Aguarda healthchecks (até 3 min).
9. Mostra URLs e próximos passos.

---

## Verificações

Depois do bootstrap:

```bash
make health    # checa todos os serviços
make ps        # status containers
make logs      # tail -f de tudo
```

### Endpoints locais

| Serviço | URL | Notas |
|---|---|---|
| HAPI FHIR | http://localhost:8090/fhir | `/metadata` mostra CapabilityStatement |
| HAPI UI | http://localhost:8090 | Tester web |
| Snowstorm | http://localhost:8080 | `/fhir` para FHIR API |
| Elasticsearch | http://localhost:9200 | `/_cluster/health` |
| Minio API | http://localhost:9000 | S3-compatible |
| Minio UI | http://localhost:9001 | user/pass do `.env` |
| Langfuse | http://localhost:3000 | criar conta no primeiro acesso |
| Adminer | http://localhost:8081 | só sobe com `docker compose --profile debug up -d` |
| Postgres | localhost:5432 | `make db-shell` para psql |
| Redis | localhost:6379 | `redis-cli` |

---

## Primeiros passos após bootstrap

```bash
make health                              # verifica saúde dos 7 serviços
make test                                # 289 testes unitários
make test-int                            # 3 testes integration (HAPI testcontainer ~90s 1ª run)
make test-e2e                            # 6 testes e2e (requer ANTHROPIC_API_KEY + stack up)
make api                                 # FastAPI em http://localhost:8000
make worker                              # Dramatiq worker
make proxy                               # ProxyLLM local (sem API key)
make docs                                # gera PPTX + DOCX em docs/
```

Para os prompts de implementação de cada fase, ver `CLAUDE.md` §10.

---

## Carregando SNOMED CT no Snowstorm (opcional na Fase 0)

Snowstorm sobe vazio. Para carregar SNOMED CT BR Edition:

1. Baixe a release oficial RF2 do SNOMED International (requer associação Brasil — Ministério da Saúde via DataSUS é o titular).
2. Coloque o ZIP em `data/snomed-import/`.
3. Importe via API:

```bash
curl -X POST http://localhost:8080/imports \
  -H 'Content-Type: application/json' \
  -d '{"branchPath": "MAIN", "createCodeSystemVersion": true, "type": "SNAPSHOT"}'
# Recebe um {importId}, depois:
curl -X POST http://localhost:8080/imports/{importId}/archive \
  -F file=@/app/import/SnomedCT_BR_Edition_xxx.zip
```

Documentação completa: https://github.com/IHTSDO/snowstorm/blob/master/docs/loading-snomed.md

---

## Carregando BR Core no HAPI

Para que `$validate` funcione contra BR Core:

1. Descomente as linhas de `hapi.fhir.implementationguides.brcore.*` no `docker-compose.yml`.
2. `make restart` no HAPI.
3. HAPI baixa o pacote do registry FHIR e instala automaticamente no boot.
4. Verifique:

```bash
curl http://localhost:8090/fhir/StructureDefinition?url=http://hl7.org.br/fhir/r4/core/StructureDefinition/BRCorePatient
```

---

## Troubleshooting

| Sintoma | Causa provável | Solução |
|---|---|---|
| `elasticsearch` reinicia em loop | `vm.max_map_count` baixo | `sudo sysctl -w vm.max_map_count=262144` |
| `snowstorm` UNHEALTHY após 5 min | ES não está pronto | `make logs-snowstorm` para ver erro real; geralmente memória |
| `hapi` com 503 em `/fhir/metadata` | Postgres ainda subindo | aguarde mais 30s; `make health` |
| `langfuse` 502 | NEXTAUTH_SECRET vazio | rodar `make secrets` e atualizar `.env` |
| `make health` mostra `jq: command not found` | jq não instalado | `apt install jq` ou `brew install jq` |
| Porta já em uso | conflito com outro serviço | mudar `*_PORT` no `.env` |
| `uv sync` falha em torch/transformers | pouco espaço em `/tmp` ou rede ruim | `UV_CACHE_DIR=/path/to/big/disk uv sync` |

---

## O que está implementado (tag v2.1)

Todos os packages e apps implementados com gates verdes. Pipeline e2e validado com Anthropic real + HAPI real:

- `packages/core` — Settings, LLMRouter, tipos, exceções, logging
- `packages/swagger_lens` — Parser OpenAPI 2.0/3.x completo com hypothesis
- `packages/fhir_forge` — Agente LangGraph de 5 nós + checkpointer Postgres
- `packages/term_mapper` — SNOMED/LOINC/CID-10/TUSS com cache Redis
- `packages/connectors` — HAPI client (tenacity retry) + RNDS client (mTLS)
- `packages/eval` — EvalRunner com métricas precision/recall + relatório rich
- `packages/mcp_server` — 6 FastMCP tools para integração com Claude
- `apps/api` — FastAPI gateway com 4 routers + OTEL + auth middleware
- `apps/worker` — Dramatiq workers com DLQ + idempotência Redis
- `proxyllm/` — Proxy local /v1/messages (mock FHIR ou Ollama) para dev sem API key
- `tests/e2e/` — 6 testes e2e: spec OpenAPI → LangGraph → HAPI $validate → Bundle

**E2E validado (Abril 2026):** 7 endpoints mapeados, fix_node ativado, Bundle com 0 erros fatais no HAPI.

**Ainda não incluído (trabalho futuro):**

- IG sources em `ig/input/fsh/` (SUSHI/IG Publisher)
- Migrations Alembic
- Workflows GitHub Actions (`ci.yml`, `ig-build.yml`)
- Helm charts e Terraform

---

## Arquivos neste pacote

```
fhir-forge/
├── README-bootstrap.md          ← este arquivo
├── docker-compose.yml           ← stack principal (versões pinadas)
├── docker-compose.override.yml  ← sobrescritas dev (logs verbose)
├── pyproject.toml               ← uv workspace + ruff/mypy/pytest config
├── Makefile                     ← atalhos (make help)
├── .env.example                 ← template de variáveis
├── .gitignore
├── proxyllm/
│   ├── server.py                ← proxy /v1/messages (mock ou Ollama)
│   └── Dockerfile               ← imagem para docker compose --profile proxyllm
├── scripts/
│   ├── bootstrap.sh             ← setup idempotente
│   ├── postgres-init.sh         ← cria múltiplas DBs no boot
│   ├── generate_pptx.py         ← gera apresentação PPTX de arquitetura
│   └── generate_docx.py         ← gera documento DOCX de arquitetura
├── tests/e2e/
│   └── test_convert_e2e.py      ← 6 testes end-to-end
└── docs/
    ├── fhir-forge-arquitetura.pptx  ← apresentação 17 slides
    └── fhir-forge-arquitetura.docx  ← documento 15 capítulos
```
