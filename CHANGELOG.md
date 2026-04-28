# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · Versionamento [SemVer](https://semver.org/lang/pt-BR/).

## [v2.1] — 2026-04-28

Pós-correção do `Bundle/$validate` no spec real `jsonAPI/schedules_1.json` (1.81 MB, 19 endpoints): saímos de **16 erros fatais + 32 warnings dom-6** para **0 erros + 0 warnings**.

### Adicionado

- `packages/fhir_forge/src/fhir_forge/nodes/_helpers.py` — utilitários puros: `slugify()` para ids derivados de `operation_id` + `repair_mojibake()` / `sanitize_resource()` para recuperação UTF-8 best-effort.
- `tests/integration/test_bundle_validation.py` — 3 casos contra HAPI testcontainer real: `Bundle/$validate` com 0 fatais, 0 warnings dom-6, todos `fullUrl` em UUID v4.
- `tests/regression/test_golden_bundles.py` — 4 invariantes estruturais (`_assert_structural_invariants`), cada uma amarrada a um bug histórico (fullUrl, ids únicos, narrativa, mojibake).
- `tests/unit/test_fhir_forge_helpers.py`, `tests/unit/test_bundle_node.py`, `tests/unit/test_fix_node.py` — preencher gaps de cobertura.
- `CHANGELOG.md` — este arquivo.

### Corrigido

- `bundle_node.py`: `entry.fullUrl` agora gera `uuid.uuid4()` real. Antes concatenava `urn:uuid:` + `id`, violando FHIR R4 (UUIDs must be valid and lowercase) → 16 erros fatais no `$validate`.
- `bundle_node.py`: injeta narrativa mínima `text.div` em DomainResources sem narrativa (fecha os 32 warnings dom-6).
- `mapping_node.py`: `id` do recurso é derivado de `slugify(operation_id)` com dedup automático (`-2`, `-3`); o `id` que o LLM sugere é descartado. Resolve duplicidades como `bookTime-example` aparecendo 2x.
- `mapping_node.py` + `fix_node.py`: `sanitize_resource()` aplicado na saída do LLM, recuperando mojibake típico (`JoÃ£o` → `João`).
- `apps/api/src/api/routers/mcp.py`: catch de `AttributeError` no `mount_mcp` para que versão incompatível de `fastmcp` não quebre o `lifespan` do uvicorn.
- `apps/web/nginx.conf`: `client_max_body_size 50m` (specs ~2 MB davam 413) + `proxy_read_timeout` / `proxy_send_timeout` 1800 s (cadeias longas de LLM passavam de 300 s).

### Mudanças

- System prompt de `mapping_node.py` e `fix_node.py` reforçado com regra explícita: *"Use proper UTF-8 for accented characters; never produce mojibake"*.
- `tests/regression/test_golden_bundles.py`: golden pairs regenerados com o novo formato (UUID v4 fullUrls, slug ids, narrativa). Asserções estruturais novas previnem regressão dos bugs corrigidos.
- `tests/unit/test_extractor.py`, `tests/unit/test_llm_router.py`, `tests/unit/test_parser.py`, `tests/unit/test_settings.py`: import-order pré-existente normalizado por `ruff --fix`.

### Métricas

| | v2 | v2.1 |
|---|---:|---:|
| Unit tests | 252 | **289** |
| Integration tests | 0 | **3** (HAPI testcontainer) |
| Regression tests | 7 | **7** (endurecidos) |
| E2E tests | 6 | 6 |
| Cobertura global | 91% | **91%** |
| Erros fatais no smoke real | 16 | **0** |
| Warnings dom-6 no smoke real | 32 | **0** |
| ruff / mypy strict | clean | clean |

### Sequência de commits

1. `feat(fhir_forge): add slug + mojibake helpers`
2. `fix(bundle_node): use real UUID v4 for entry.fullUrl`
3. `fix(mapping_node): unique slug ids, UTF-8 prompt, sanitize`
4. `fix(fix_node): UTF-8 prompt + sanitize LLM output`
5. `fix(api+web): MCP attr-error fallback, nginx body & timeouts`
6. `feat(bundle_node): inject minimal narrative to fix dom-6`
7. `test(regression): add structural invariants per past bug`
8. `test(regression): refresh golden bundles with v2.1 format`
9. `style: fix import order in pre-existing test files`
10. `docs(CLAUDE.md): update §11 status to tag v2.1`

---

## [v2] — 2026-04-XX

Implementação inicial das 9 fases do `CLAUDE.md` §10. Pipeline `OpenAPI → LangGraph (5 nós) → HAPI $validate → Bundle` validado e2e com Anthropic + HAPI reais.

- 9 packages/apps completos: `core`, `swagger_lens`, `fhir_forge`, `term_mapper`, `connectors`, `eval`, `mcp_server`, `apps/api`, `apps/worker`.
- 252 unit tests + 6 e2e tests passando, 91% cobertura, ruff + mypy strict clean.
- Stack Docker: 7 serviços validados (HAPI 8.4.0-2, Snowstorm 7.5.0, ES 7.17.24, Postgres pgvector pg16, Redis 7.4, Minio, Langfuse 2.x).
- ProxyLLM local em `/v1/messages` (mock FHIR ou Ollama) para desenvolvimento sem API key.
