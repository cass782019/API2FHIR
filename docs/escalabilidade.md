# Plano: Escalabilidade — FHIR-Forge v2.1 → Produção

## Context

O FHIR-Forge v2.1 é uma stack de desenvolvimento local completamente funcional (**289 unit + 3 integration + 7 regression + 6 e2e**, 91% cobertura), mas **não está pronta para produção**. Problemas identificados via exploração direta do código:

| Problema | Arquivo | Linha | Impacto |
|---|---|---|---|
| `AsyncClient()` criado por chamada | hapi_client.py | 62 (`_request`) | N conexões TCP novas por request |
| `AsyncClient()` criado por chamada | snowstorm_client.py | 35, 71 | idem |
| `AsyncClient()` criado por chamada | hapi_valueset_client.py | 30, 56 | idem |
| `AsyncClient()` criado por chamada | rnds_client.py | 71, 94, 113 | idem + SSLContext reconstruído por chamada |
| `AsyncClient()` criado por chamada | validation_node.py | 23 | idem — omitido da fase 5 original |
| `retry_async` de `resilience.py` nunca aplicado | resilience.py | 24 | hapi_client usa `@tenacity.retry` inline; snowstorm/valueset/rnds não têm retry |
| `fhir_circuit_breaker` definido, nunca usado | resilience.py | 17 | nenhum cliente aplica o breaker |
| `AsyncCircuitBreaker` com `asyncio.run()` dentro de executor | resilience.py | 72 | `RuntimeError` em produção — segundo event loop em thread de executor |
| `MemorySaver()` como default LangGraph | service.py | 33 | sem persistência em falhas |
| Endpoints mapeados serialmente | mapping_node.py | ~170 | latência = N × latência_unitária |
| Recursos validados serialmente | validation_node.py | ~51 | idem |
| Chamada LLM sem timeout | mapping_node.py, fix_node.py | — | worker pode bloquear 5 min |
| `worker_concurrency=4` nunca lida | settings.py / main.py | — | sempre 1 processo |
| Sem rate limiting | main.py (api) | — | qualquer cliente satura /convert |
| `allow_origins=["*"]` | main.py (api) | 55 | CORS aberto em produção |
| Token RNDS em memória | rnds_client.py | — | N processos = N auth calls |
| Sem Dockerfiles para apps | — | — | bloqueador de K8s e prod |
| Sem limites de memória no compose | docker-compose.yml | — | OOM cascata no host |
| Sem healthcheck Langfuse | docker-compose.yml | — | falha silenciosa |

**Princípio:** cada fase tem um gate de saída binário. Não avançar com gate vermelho.

---

## Status pós-v2.1 (2026-04-28) — o que MUDOU vs. quando este plano foi escrito

A tag v2.1 corrigiu bugs de **qualidade do output FHIR** (não de produção). Resumo do que mudou no código tocado por este plano:

| Arquivo | Mudança v2.1 | Impacto neste plano |
|---|---|---|
| `bundle_node.py` | UUID v4 real em `fullUrl` + `_ensure_narrative()` (text.div) | Mesma estrutura — passos da Fase 1 não-afetados |
| `mapping_node.py` | `sanitize_resource()` + `slugify()` + dedup ids; novo `seen_ids: set[str]` | **Loop antes serial em ~170 agora vai até ~205**; o gather do Passo 1.4a precisa preservar `seen_ids` (state mutável) |
| `fix_node.py` | `sanitize_resource()` na resposta do LLM | Loop antes em 76-85 agora 78-89; gather do 1.4a precisa preservar a chamada de sanitize |
| `_helpers.py` (novo) | utilitários puros | Sem impacto neste plano |
| `apps/api/.../mcp.py` | catch de `AttributeError` | Sem impacto |
| `apps/web/nginx.conf` | `client_max_body_size 50m`, timeouts 1800s | **Substitui parcialmente o Passo 2.3** (Nginx reverse proxy): a config local existe, mas falta TLS + rate-limit de rede |

**O que NÃO mudou em v2.1 e segue como TODO deste plano:**

- Pool httpx (Passo 1.1) — ainda criado por chamada em todos os 5 clientes.
- Circuit breaker / retry_async (Passo 1.2) — ainda definidos e nunca aplicados.
- LLM singleton (Passo 1.3) — `get_anthropic_client()` ainda instancia por chamada.
- `asyncio.gather` nos nodes (Passo 1.4a) — ainda serial.
- `AsyncPostgresSaver` default (Passo 1.4b) — ainda `MemorySaver()`.
- Timeout de LLM (Passo 1.5) — `_map_endpoint`/`_fix_resource` sem `wait_for`.
- `worker_concurrency` (Passo 1.6) — ainda hardcoded 2 no Makefile.
- Rate limit + CORS (Passo 1.7) — ainda `allow_origins=["*"]`.
- Token RNDS em Redis (Passo 1.8) — ainda em memória.
- Dockerfiles para apps (Passo 1.9) — não criados.
- Limites de memória, healthcheck Langfuse, PgBouncer, Prometheus/Grafana (Fase 2) — pendentes.
- Helm + CI/CD (Fase 3) — pendentes.

**Recomendação de ordem revisada:** o ROI do Passo 2.1 (limites de memória) subiu — agora que o frontend permite specs grandes (50 MB), um pico legítimo pode estourar a JVM do HAPI sem limites. Considerar 2.1 antes do 1.4a.

---

## FASE 1 — Hardening do Código (1–2 dias)

Sem mudança de infraestrutura. Os **289 testes unitários + 3 integration + 7 regression + 6 e2e** devem continuar passando ao final de cada passo.

---

### Passo 1.1 — httpx Connection Pool compartilhado

**Contexto:** `httpx.AsyncClient()` criado dentro de cada método de cada cliente. A cada chamada HTTP: nova conexão TCP, novo TLS handshake, sem reutilização. Sob carga = N × overhead de conexão.

**Arquivos (5 clientes HTTP com AsyncClient por chamada):**

- [packages/connectors/src/connectors/hapi_client.py](../packages/connectors/src/connectors/hapi_client.py) — `_request()` linha 62
- [packages/connectors/src/connectors/rnds_client.py](../packages/connectors/src/connectors/rnds_client.py) — `get_token()` linha 71, `submit_document()` linha 94, `get_document()` linha 113; também cachear `SSLContext`
- [packages/term_mapper/src/term_mapper/snowstorm_client.py](../packages/term_mapper/src/term_mapper/snowstorm_client.py) — `find_concept()` linha 35, `translate()` linha 71
- [packages/term_mapper/src/term_mapper/hapi_valueset_client.py](../packages/term_mapper/src/term_mapper/hapi_valueset_client.py) — `expand()` linha 30, `lookup()` linha 56
- [packages/fhir_forge/src/fhir_forge/nodes/validation_node.py](../packages/fhir_forge/src/fhir_forge/nodes/validation_node.py) — `_validate_resource()` linha 23 (omitido na Fase 5 original)

**Mudança em `hapi_client.py`** — o `AsyncClient` é criado dentro de `_request()` (linha 62). Mover para `__init__`:

```python
# ANTES — _request() cria novo client por chamada (linha 62):
async def _request(self, method, url, *, json=None, params=None):
    async with httpx.AsyncClient(timeout=self._timeout) as http:
        resp = await http.request(method, url, json=json, params=params)
    return resp

# DEPOIS — _client compartilhado no __init__, _request usa self._client:
class HapiFhirClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(min=1, max=10),
        reraise=True,
        retry=tenacity.retry_if_exception_type(httpx.TransportError),
    )
    async def _request(self, method, url, *, json=None, params=None):
        resp = await self._client.request(method, url, json=json, params=params)
        return resp
```

**Mudança em `validation_node.py`** — extrair o `AsyncClient` para fora de `_validate_resource()`:

```python
# ANTES — novo AsyncClient por recurso validado (linha 23):
async with httpx.AsyncClient(timeout=30.0) as http:
    resp = await http.post(url, json=resource)

# DEPOIS — receber client como parâmetro:
async def _validate_resource(
    resource: dict, hapi_base_url: str, *, http: httpx.AsyncClient
) -> list[str]:
    resp = await http.post(f"{hapi_base_url}/{resource_type}/$validate", json=resource)
    ...

async def validation_node(state, *, hapi_base_url=None):
    base_url = hapi_base_url or app_settings.hapi_base_url
    async with httpx.AsyncClient(
        timeout=30.0,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    ) as http:
        # Agora o mesmo client é reutilizado para todos os recursos
        for resource in resources:
            errors = await _validate_resource(resource, base_url, http=http)
```

**Extra para `rnds_client.py`** — cachear SSLContext (hoje reconstruído por request):

```python
class RndsClient:
    def __init__(self, ...) -> None:
        self._ssl_ctx = self._build_ssl_context()   # uma vez
        self._client = httpx.AsyncClient(
            verify=self._ssl_ctx,
            timeout=30.0,
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
        )

    def _build_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_cert_chain(settings.rnds_cert_path, password=settings.rnds_cert_password)
        return ctx
```

**Registro no lifespan da API** (`apps/api/src/api/main.py`):

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    hapi = HapiFhirClient(settings.hapi_base_url)
    app.state.hapi = hapi
    yield
    await hapi.aclose()
```

**Testes a criar/atualizar:**

```python
# tests/unit/test_hapi_client.py
def test_client_reused_across_calls(hapi_client):
    """_client instanciado uma vez, não por chamada."""
    id_before = id(hapi_client._client)
    id_after  = id(hapi_client._client)
    assert id_before == id_after

def test_limits_configured(hapi_client):
    assert hapi_client._client.limits.max_connections == 20
    assert hapi_client._client.limits.max_keepalive_connections == 10
```

---

### Passo 1.2 — Ativar Circuit Breaker e Retry

**Contexto:** `resilience.py` define `retry_async` e `fhir_circuit_breaker` mas nenhum método os usa. O `AsyncCircuitBreaker` wrapper tem antipattern: chama `asyncio.run()` dentro de `loop.run_in_executor()` — cria segundo event loop na thread do executor, o que levanta `RuntimeError`.

**Mudança em `resilience.py`** — remover a classe `AsyncCircuitBreaker` inteira (linhas 47-74); usar `call_async()` nativo do pybreaker:

```python
# REMOVER — classe AsyncCircuitBreaker (linhas 47-74)
# Antipattern: asyncio.run() dentro de run_in_executor() cria 2º event loop -> RuntimeError

# MANTER sem alteração — fhir_circuit_breaker e retry_async já corretos.

# NÃO adicionar call_with_breaker — pybreaker >= 0.7 expõe call_async() nativo:
#   await fhir_circuit_breaker.call_async(coro_func, *args, **kwargs)
# A função é passada como argumento, não a coroutine já instanciada.
```

**Aplicar em `hapi_client.py`** — integrar `call_async` no `_request()` existente:

```python
from connectors.resilience import fhir_circuit_breaker

class HapiFhirClient:
    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(min=1, max=10),
        reraise=True,
        retry=tenacity.retry_if_exception_type(httpx.TransportError),
    )
    async def _request(self, method: str, url: str, *, json=None, params=None):
        # Passa a função + args, NÃO a coroutine (call_async a instancia internamente)
        return await fhir_circuit_breaker.call_async(
            self._client.request, method, url, json=json, params=params
        )
```

> **Atenção:** `call_async(func, *args)` recebe a **função callable**, não a coroutine já criada. `call_async(self._client.request, "GET", url)` ✔ — `call_async(self._client.request("GET", url))` ✗ (breaker não registra falha).

**Aplicar em `snowstorm_client.py`:** `@retry_async(attempts=2)` em `find_concept` e `translate`.

**Testes a criar:**

```python
# tests/unit/test_resilience.py
async def test_retry_succeeds_after_failures():
    """Falha 2x depois sucesso -> chamado 3x total."""
    call_count = 0
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TransportError("timeout")
        return {"ok": True}
    decorated = retry_async(attempts=3)(flaky)
    result = await decorated()
    assert result == {"ok": True}
    assert call_count == 3

async def test_circuit_breaker_opens_after_failures():
    """5 falhas consecutivas -> CircuitBreakerError na 6ª chamada."""
    breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)

    async def fail():
        raise RuntimeError("falha simulada")

    for _ in range(5):
        with pytest.raises(RuntimeError):
            await breaker.call_async(fail)  # call_async — API pública

    with pytest.raises(pybreaker.CircuitBreakerError):
        await breaker.call_async(fail)

# tests/unit/test_hapi_client.py
async def test_request_retries_on_transport_error():
    """_request falha 2x com TransportError, sucesso na 3ª -> retorna Response."""
    # respx não intercepta self._client diretamente — mockar o transport do AsyncClient
    call_count = 0

    async def mock_send(request, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TransportError("net")
        return httpx.Response(200, json={"resourceType": "OperationOutcome", "issue": []})

    client = HapiFhirClient("http://hapi:8090/fhir")
    client._client._transport = httpx.AsyncMockTransport(handler=mock_send)
    result = await client.validate({"resourceType": "Patient", "id": "p1"})
    assert result.valid is True
    assert call_count == 3
```

---

### Passo 1.3 — LLM Client singleton + fallback chain

**Contexto:** `llm_router.py` cria `anthropic.AsyncAnthropic(api_key=key)` a cada chamada de `get_anthropic_client()` (linha 45) — sem cache. Sem fallback automático se Anthropic falhar.

**Mudança em `llm_router.py`** — adicionar cache lazy e `create_message()` com fallback:

```python
class LLMRouter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # Cache dos clientes — criados uma única vez (lazy)
        self._anthropic_client: anthropic.AsyncAnthropic | None = None
        self._vllm_client: anthropic.AsyncAnthropic | None = None

    def get_anthropic_client(self, fast: bool = False) -> anthropic.AsyncAnthropic:
        """Retorna sempre o mesmo cliente (singleton por processo)."""
        if self._anthropic_client is None:
            key = self._settings.anthropic_api_key.get_secret_value()
            if not key:
                raise ConfigurationError("ANTHROPIC_API_KEY not set")
            self._anthropic_client = anthropic.AsyncAnthropic(api_key=key)
        return self._anthropic_client

    def _get_vllm_client(self) -> anthropic.AsyncAnthropic:
        if self._vllm_client is None:
            self._vllm_client = anthropic.AsyncAnthropic(
                base_url=self._settings.vllm_base_url,
                api_key=self._settings.vllm_api_key or "unused",
            )
        return self._vllm_client

    async def create_message(self, *, phi_data: bool = False, **kwargs) -> anthropic.types.Message:
        """Tenta Anthropic, faz fallback para vLLM em caso de falha."""
        providers = [self.get_anthropic_client, self._get_vllm_client]
        if phi_data or not self._settings.feature_allow_phi_egress:
            providers = [self._get_vllm_client]
        last_exc: Exception | None = None
        for get_provider in providers:
            try:
                client = get_provider()
                return await asyncio.wait_for(
                    client.messages.create(**kwargs), timeout=60.0
                )
            except Exception as exc:
                log.warning("llm_provider_failed", provider=get_provider.__name__, error=str(exc))
                last_exc = exc
        raise MappingError(f"Todos os providers LLM falharam: {last_exc}")
```

**Testes a criar:**

```python
# tests/unit/test_llm_router.py
def test_singleton_anthropic_client(router):
    """Mesmo objeto retornado em chamadas consecutivas."""
    assert router.get_anthropic_client() is router.get_anthropic_client()

def test_phi_always_vllm(router_phi_egress_off):
    """PHI=True + feature_allow_phi_egress=False -> vLLM (localhost)."""
    # selected_provider já garante isso; create_message deve chamar vLLM
    assert router_phi_egress_off.selected_provider(phi_data=True) == LLMProvider.VLLM

async def test_fallback_to_vllm_on_anthropic_failure(router, mock_anthropic_fails, mock_vllm_ok):
    """Anthropic levanta excecao -> cai para vLLM."""
    result = await router.create_message(model="claude-opus-4-7", messages=[...])
    assert result is not None
    mock_vllm_ok.assert_called_once()
```

---

### Passo 1.4 — LangGraph: paralelo + persistencia real

#### 1.4a — asyncio.gather nos nos

**Contexto:** `mapping_node.py` linhas 170-181 e `validation_node.py` linhas 51-60 e `fix_node.py` linhas 76-85 iteram serialmente. Com 7 endpoints = 7 chamadas LLM em série. Com `asyncio.gather` = 1 chamada de tempo máximo.

**Mudança em `mapping_node.py`** — `endpoints_to_process` são operation IDs (strings), não objetos Endpoint. **Atenção v2.1:** o loop atual (linhas ~177-205) tem `sanitize_resource()` + `slugify()` + dedup de ids via `seen_ids` set. O gather precisa preservar essa lógica e centralizar a atribuição de ids **fora** do gather (caso contrário corridas no `seen_ids` quebram dedup).

```python
# ANTES v2.1 (serial — linhas ~170-205, com sanitize + slug):
seen_ids: set[str] = set()
for op_id in op_ids:
    ep = endpoint_map.get(op_id)
    if ep is None:
        continue
    try:
        resource = await _map_endpoint(client, model, ep)
    except MappingError as exc:
        log.warning("mapping_failed", op_id=op_id, reason=str(exc))
        continue
    if resource.get("resourceType") == "Basic":
        continue
    resource = sanitize_resource(resource)
    base_id = slugify(op_id) or "resource"
    rid, n = base_id, 1
    while rid in seen_ids:
        n += 1
        rid = f"{base_id}-{n}"
    seen_ids.add(rid)
    resource["id"] = rid
    resources.append(resource)

# DEPOIS (paralelo) — atribuir id NO POST-PROCESSAMENTO, não dentro do gather:
async def _map_one(op_id: str) -> tuple[str, dict[str, Any]] | None:
    ep = endpoint_map.get(op_id)
    if ep is None:
        return None
    try:
        resource = await _map_endpoint(client, model, ep)
    except MappingError as exc:
        log.warning("mapping_failed", op_id=op_id, reason=str(exc))
        return None
    if resource.get("resourceType") == "Basic":
        return None
    return op_id, sanitize_resource(resource)

raw = await asyncio.gather(*[_map_one(op_id) for op_id in op_ids], return_exceptions=True)
seen_ids: set[str] = set()
resources: list[dict[str, Any]] = []
for item in raw:
    if not isinstance(item, tuple):
        continue
    op_id, resource = item
    base_id = slugify(op_id) or "resource"
    rid, n = base_id, 1
    while rid in seen_ids:
        n += 1
        rid = f"{base_id}-{n}"
    seen_ids.add(rid)
    resource["id"] = rid
    resources.append(resource)
```

**Mudança em `validation_node.py`** — reutilizar o `http` do Passo 1.1 e usar gather:

```python
# DEPOIS (paralelo — após ter http como parâmetro do Passo 1.1):
results = await asyncio.gather(
    *[_validate_resource(r, base_url, http=http) for r in resources],
    return_exceptions=True,
)
```

**Mudança em `fix_node.py`** — linhas ~78-89 também em série. **Atenção v2.1:** o loop agora aplica `sanitize_resource(result)` antes do `fixed.append`. Preservar:

```python
# DEPOIS (paralelo) — sanitize antes de retornar:
async def _fix_one(resource: dict) -> dict:
    rid = resource.get("id", resource.get("resourceType", "?"))
    resource_errors = [e for e in errors if e.startswith(f"{rid}:")]
    try:
        result = await _fix_resource(client, model, resource, resource_errors)
        return sanitize_resource(result)
    except MappingError as exc:
        log.warning("fix_failed", resource_id=rid, reason=str(exc))
        return resource  # mantém original

fixed = list(await asyncio.gather(*[_fix_one(r) for r in invalid], return_exceptions=False))
```

#### 1.4b — AsyncPostgresSaver como padrão

**Mudança em `service.py`** — usar `async with` (não `__aenter__()` diretamente):

```python
# ANTES (linha 32-33):
if checkpointer is None:
    checkpointer = MemorySaver()  # sem persistência

# DEPOIS — reestruturar convert() para manter o context manager aberto durante ainvoke:
async def convert(swagger_spec, job_id, *, checkpointer=None, ...) -> dict:
    from core.settings import settings as app_settings

    if checkpointer is not None:
        # Checkpointer externo (testes) — usar diretamente
        return await _run_graph(swagger_spec, job_id, checkpointer=checkpointer, ...)

    if app_settings.langgraph_db_url:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        async with AsyncPostgresSaver.from_conn_string(app_settings.langgraph_db_url) as saver:
            return await _run_graph(swagger_spec, job_id, checkpointer=saver, ...)
    else:
        return await _run_graph(swagger_spec, job_id, checkpointer=MemorySaver(), ...)

async def _run_graph(swagger_spec, job_id, *, checkpointer, client=None, model=None, hapi_base_url=None):
    """Extrai o bloco de build_graph + ainvoke para reutilização."""
    compiled = build_graph(client=client, model=model, hapi_base_url=hapi_base_url, checkpointer=checkpointer)
    ...  # resto do código atual de convert()
```

**Testes a criar:**

```python
# tests/unit/test_mapping_node.py
async def test_endpoints_mapped_in_parallel():
    """Todos os op_ids mapeados simultaneamente (< 0.02s entre starts)."""
    call_times: list[float] = []

    async def slow_map(client, model, ep):
        call_times.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.05)
        return {"resourceType": "Patient", "id": ep.operation_id}

    with patch("fhir_forge.nodes.mapping_node._map_endpoint", side_effect=slow_map):
        await mapping_node(build_state(op_ids=["op1", "op2", "op3"]))

    assert max(call_times) - min(call_times) < 0.02, "Mapeamento nao foi paralelo"

# tests/unit/test_graph_transitions.py — regressao total obrigatoria
async def test_validation_failure_triggers_fix_node(mock_hapi_returns_error):
    ...  # comportamento existente deve ser preservado
```

---

### Passo 1.5 — Timeout por no LangGraph

**Contexto:** A chamada LLM sem timeout está dentro das funções helper: `_map_endpoint()` em `mapping_node.py` (linha 119) e `_fix_resource()` em `fix_node.py` (linha 35). Um hang bloqueia o worker Dramatiq até o `time_limit` do actor (5 min). Com 4 workers pendurados = fila parada.

**Mudança em `mapping_node.py` — dentro de `_map_endpoint()`:**

```python
# ANTES (linha 119-124 de mapping_node.py):
async def _map_endpoint(client, model, endpoint):
    ...
    response = await client.messages.create(
        model=model, max_tokens=1024, system=_SYSTEM_PROMPT, messages=messages
    )

# DEPOIS — timeout dentro de _map_endpoint (não no nó):
async def _map_endpoint(client, model, endpoint):
    ...
    try:
        response = await asyncio.wait_for(
            client.messages.create(model=model, max_tokens=1024, system=_SYSTEM_PROMPT, messages=messages),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        raise MappingError(
            f"LLM timeout apos 60s",
            endpoint=endpoint.path,
            reason="timeout",
        )
```

**Mudança em `fix_node.py` — dentro de `_fix_resource()` (linha 35):**

```python
# DEPOIS — mesmo padrão:
async def _fix_resource(client, model, resource, errors):
    ...
    try:
        response = await asyncio.wait_for(
            client.messages.create(model=model, max_tokens=1024, system=_FIX_SYSTEM, messages=[...]),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        raise MappingError("LLM fix timeout apos 60s", endpoint=resource.get("id", ""), reason="timeout")
```

**Testes a criar:**

```python
# tests/unit/test_mapping_node.py
async def test_llm_timeout_raises_mapping_error(mock_anthropic_client):
    """wait_for em _map_endpoint lança TimeoutError -> endpoint descartado pelo gather."""
    # NÃO usar asyncio.sleep(120) — o teste levaria 60s reais.
    # Patch wait_for para lançar TimeoutError imediatamente.
    with patch("fhir_forge.nodes.mapping_node.asyncio.wait_for",
               side_effect=asyncio.TimeoutError):
        state = await mapping_node(build_state(op_ids=["op1"]), client=mock_anthropic_client)
    assert state["fhir_resources"] == []  # descartado pelo gather, não propaga

# tests/unit/test_fix_node.py — mesmo padrão:
async def test_fix_timeout_keeps_original_resource(mock_anthropic_client, sample_invalid_resource):
    with patch("fhir_forge.nodes.fix_node.asyncio.wait_for",
               side_effect=asyncio.TimeoutError):
        state = await fix_node(build_state_with_invalid(sample_invalid_resource),
                               client=mock_anthropic_client)
    # Fix falhou -> recurso original mantido (comportamento atual do except MappingError)
    assert len(state["fhir_resources"]) == 1
```

---

### Passo 1.6 — Fiar worker_concurrency

**Contexto:** `settings.worker_concurrency = 4` definido em Settings mas Dramatiq sobe com defaults (1 processo). Makefile usa `--processes 2` hardcoded.

**Mudança em `apps/worker/src/worker/main.py`** — adicionar função `_build_dramatiq_command()` e bloco `__main__`:

```python
# Adicionar ao final de worker/main.py:
import sys

def _build_dramatiq_command() -> list[str]:
    """Constrói o comando dramatiq com worker_concurrency do settings."""
    from core.settings import settings as _s
    return [
        sys.executable, "-m", "dramatiq",
        "worker.main",        # importa este módulo → configure_broker() registra os actors
        f"--processes={_s.worker_concurrency}",
        "--threads=4",
    ]

if __name__ == "__main__":
    import subprocess
    subprocess.run(_build_dramatiq_command(), check=True)
```

> **Nota:** O módulo de entrada para o dramatiq CLI é `worker.main` (não `worker.actors.conversion` separadamente) porque `configure_broker()` já importa `worker.actors.conversion` internamente. O DLQ handler fica em `worker.dlq_handler` (não em `worker.actors.dlq_handler`).

**Atualizar `Makefile`** target `worker` (hoje: `dramatiq apps.worker.main --processes 2 --threads 4`):

```makefile
worker: ## Sobe worker Dramatiq (WORKER_CONCURRENCY lido do .env)
	$(UV) run python -m worker.main
```

**Testes a criar:**

```python
# tests/unit/test_worker_main.py (criar)
def test_dramatiq_command_uses_worker_concurrency(monkeypatch):
    """_build_dramatiq_command() reflete WORKER_CONCURRENCY do ambiente."""
    monkeypatch.setenv("WORKER_CONCURRENCY", "6")
    # Reimportar settings com env novo
    import importlib, core.settings
    importlib.reload(core.settings)
    from worker.main import _build_dramatiq_command
    cmd = _build_dramatiq_command()
    assert "--processes=6" in cmd
    assert "worker.main" in cmd

def test_dramatiq_command_default_concurrency():
    """Sem WORKER_CONCURRENCY explícito, usa o default do settings."""
    from worker.main import _build_dramatiq_command
    cmd = _build_dramatiq_command()
    # Verifica que algum --processes=N está presente
    assert any(arg.startswith("--processes=") for arg in cmd)
```

---

### Passo 1.7 — Rate limiting + CORS restrito

**Contexto:** `main.py` linha 55 tem `allow_origins=["*"]` com `allow_credentials=True` — viola a spec CORS. Sem rate limiting qualquer cliente pode saturar `/convert`.

**Adicionar ao `pyproject.toml`:**

```toml
"slowapi>=0.1.5",
"prometheus-fastapi-instrumentator>=7.0",
```

**Adicionar `cors_allowed_origins` em `settings.py`:**

```python
cors_allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
```

**Mudanca em `apps/api/src/api/main.py`:**

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS restrito:
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# No router /convert:
@router.post("/convert")
@limiter.limit("10/minute")
async def convert_endpoint(request: Request, ...): ...
```

**Testes a criar:**

```python
# tests/unit/test_routers_convert.py
async def test_rate_limit_returns_429_on_burst(async_client):
    """11 chamadas rapidas -> pelo menos 1 HTTP 429."""
    responses = [await async_client.post("/convert", json=body) for _ in range(11)]
    assert any(r.status_code == 429 for r in responses)

async def test_cors_wildcard_removed(async_client):
    """Origem nao listada -> sem Access-Control-Allow-Origin."""
    r = await async_client.options(
        "/convert",
        headers={"Origin": "https://evil.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in r.headers
```

---

### Passo 1.8 — RNDS token em Redis

**Contexto:** Token RNDS em `self._token` (memoria de processo). Com 4 workers = 4 auth calls a cada renovacao.

**Mudança em `rnds_client.py`** — extrair lógica de fetch para `_fetch_token()` (hoje inline em `get_token()`) e cachear no Redis:

```python
_TOKEN_KEY = "rnds:auth_token"

class RndsClient:
    def __init__(self, base_url, auth_url, cert_path, cert_password,
                 timeout=30.0, *, redis_client: aioredis.Redis) -> None:
        ...
        self._redis = redis_client
        # SSLContext criado uma vez (hoje reconstruído por chamada em get_token/submit/get):
        self._ssl_ctx = self._build_ssl_context()
        self._client = httpx.AsyncClient(verify=self._ssl_ctx, timeout=timeout)

    async def _fetch_token(self) -> tuple[str, int]:
        """Extrai o bloco de fetch de token de get_token() para reutilização."""
        resp = await self._client.get(f"{self._auth_url}/token")
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], data.get("expires_in", 3600)

    async def get_token(self) -> str:
        cached = await self._redis.get(_TOKEN_KEY)
        if cached:
            return cached.decode()
        token, expires_in = await self._fetch_token()
        await self._redis.setex(_TOKEN_KEY, max(expires_in - 30, 10), token)
        return token

    async def aclose(self) -> None:
        await self._client.aclose()
```

> **Nota:** A assinatura atual de `RndsClient.__init__()` não recebe `redis_client`. Ao adicionar, usar `*` para tornar keyword-only e não quebrar chamadores existentes.

**Testes a criar:**

```python
# tests/unit/test_rnds_client.py
async def test_token_cached_in_redis(rnds_client, fake_redis, mock_auth_server):
    """Segundo get_token le do Redis, nao chama auth server de novo."""
    await rnds_client.get_token()
    await rnds_client.get_token()
    assert mock_auth_server.call_count == 1

async def test_expired_token_refreshed(rnds_client, fake_redis, mock_auth_server):
    """Token expirado no Redis -> nova autenticacao."""
    await fake_redis.setex(_TOKEN_KEY, 1, "old_token")
    await asyncio.sleep(1.1)
    token = await rnds_client.get_token()
    assert token != "old_token"
```

---

### Passo 1.9 — Dockerfiles para apps

**Problema:** Sem `Dockerfile` nas apps nao e possivel docker compose prod nem Kubernetes.

**Criar `apps/api/Dockerfile`:**

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install uv --no-cache-dir

# Copiar manifests antes do código (aproveita cache Docker em mudanças de código)
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/api/ apps/api/
RUN uv sync --no-dev --package fhir-forge-api

# Imagem de produção: só Python + .venv instalado (sem uv, pip, build tools)
FROM python:3.12-slim AS production
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/apps/api /app/apps/api
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**Criar `apps/worker/Dockerfile`:**

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install uv --no-cache-dir

COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/worker/ apps/worker/
RUN uv sync --no-dev --package fhir-forge-worker

FROM python:3.12-slim AS production
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/apps/worker /app/apps/worker
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "worker.main"]
```

**Testes (build smoke):**

```bash
docker build -t fhir-forge-api:test   -f apps/api/Dockerfile .
docker build -t fhir-forge-worker:test -f apps/worker/Dockerfile .
docker run --rm fhir-forge-api:test    python -c "from api.main import app; print('API OK')"
docker run --rm fhir-forge-worker:test python -c "from worker.actors.conversion import convert_spec_actor; print('Worker OK')"
```

---

### Gate de Saida da Fase 1 (binario — verde ou vermelho)

```bash
# Zero regressoes
uv run pytest -m unit        # >= 289 passando (v2.1 baseline)
uv run pytest -m integration # >= 3 passando (test_bundle_validation novo)
uv run pytest -m regression  # 7 passando
uv run pytest -m e2e         # 6/6 passando

# Qualidade
uv run ruff check .          # 0 erros
uv run mypy packages apps    # 0 erros strict

# Pool verificado (id(c._client) == id(c._client) sempre True — verificar limites)
uv run python -c "
import httpx
from connectors.hapi_client import HapiFhirClient
c = HapiFhirClient('http://localhost:8090/fhir')
assert isinstance(c._client, httpx.AsyncClient), 'Pool nao configurado'
assert c._client.limits.max_connections == 20, f'max_connections errado: {c._client.limits.max_connections}'
assert c._client.limits.max_keepalive_connections == 10, 'keepalive errado'
print('Pool: OK')
"

# Imagens buildaveis
docker build -t fhir-forge-api:test   -f apps/api/Dockerfile .    && echo "API image: OK"
docker build -t fhir-forge-worker:test -f apps/worker/Dockerfile . && echo "Worker image: OK"
```

**Gate verde** = todos os comandos saem com codigo 0.

---

## FASE 2 — Infraestrutura Docker (2–3 dias)

Prerequisito: Gate Fase 1 verde.

---

### Passo 2.1 — Limites de memoria/CPU

**Contexto:** Nenhum servico tem `deploy.resources.limits`. Se HAPI ou ES extrapolarem, o kernel mata processos aleatorios no host.

**Mudanca em `docker-compose.yml`** — adicionar `deploy.resources` em cada servico:

| Servico | Memory limit | CPU limit |
|---|---|---|
| postgres | 2g | 1.0 |
| redis | 512m | 0.5 |
| hapi | 2g | 2.0 |
| elasticsearch | 5g | 2.0 |
| snowstorm | 4g | 2.0 |
| langfuse | 1g | 1.0 |
| minio | 1g | 0.5 |

```yaml
# Exemplo para hapi:
hapi:
  deploy:
    resources:
      limits:
        memory: 2g
        cpus: "2.0"
      reservations:
        memory: 1g
```

**Testes:**

```bash
make up
docker stats --no-stream --format "table {{.Name}}\t{{.MemLimit}}"
# Nenhum deve mostrar "0B" (sem limite)
make health
```

---

### Passo 2.2 — Healthcheck para Langfuse

**Contexto:** Langfuse e o unico servico sem healthcheck — falha silenciosa.

**Mudanca em `docker-compose.yml`:**

```yaml
langfuse:
  healthcheck:
    test: ["CMD", "curl", "-fsS", "http://localhost:3000/api/public/health"]
    interval: 30s
    timeout: 10s
    retries: 5
    start_period: 60s
```

**Testes:**

```bash
docker compose restart langfuse
sleep 35
docker inspect $(docker compose ps -q langfuse) --format '{{.State.Health.Status}}'
# deve retornar "healthy"
```

---

### Passo 2.3 — Nginx reverse proxy

**Contexto:** FastAPI e HAPI expostos diretamente no host. Sem TLS, sem gzip, sem rate limit de rede.

**Criar `nginx/nginx.conf`:**

```nginx
worker_processes auto;
events { worker_connections 1024; }

http {
    gzip on;
    gzip_types application/json application/fhir+json;
    limit_req_zone $binary_remote_addr zone=api:10m rate=20r/m;

    upstream fastapi { server api:8000; }
    upstream hapi    { server hapi:8080; }

    server {
        listen 443 ssl;
        ssl_certificate     /etc/nginx/certs/server.crt;
        ssl_certificate_key /etc/nginx/certs/server.key;

        location / {
            limit_req zone=api burst=5 nodelay;
            proxy_pass http://fastapi;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Request-ID    $request_id;
        }

        location /fhir-direct/ {
            allow 172.0.0.0/8;
            deny all;
            proxy_pass http://hapi/fhir/;
        }
    }

    server {
        listen 80;
        return 301 https://$host$request_uri;
    }
}
```

**Criar `nginx/gen-certs.sh`:**

```bash
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx/certs/server.key \
    -out nginx/certs/server.crt \
    -subj "/CN=localhost"
```

**Adicionar ao `docker-compose.yml`:**

```yaml
nginx:
  image: nginx:1.27-alpine
  ports: ["80:80", "443:443"]
  volumes:
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    - ./nginx/certs:/etc/nginx/certs:ro
  depends_on:
    api:
      condition: service_healthy
  networks:
    - forge-net
```

**Testes:**

```bash
bash nginx/gen-certs.sh && make up
curl -k https://localhost/health          # 200
curl -k https://localhost/fhir/metadata  # 200
for i in $(seq 1 25); do curl -sk -o /dev/null -w "%{http_code}\n" https://localhost/convert; done
# Deve incluir 429
```

---

### Passo 2.4 — PgBouncer

**Contexto:** 4 workers × 4 threads = ate 16 conexoes ao Postgres. Com API uvicorn multi-worker facilmente > 50. Postgres default `max_connections=100`.

**Adicionar ao `docker-compose.yml`:**

```yaml
pgbouncer:
  image: bitnami/pgbouncer:1.23
  environment:
    POSTGRESQL_HOST: postgres
    POSTGRESQL_PORT: 5432
    POSTGRESQL_DATABASE: forge
    POSTGRESQL_USERNAME: ${POSTGRES_USER:-forge}
    POSTGRESQL_PASSWORD: ${POSTGRES_PASSWORD}
    PGBOUNCER_POOL_MODE: transaction
    PGBOUNCER_MAX_CLIENT_CONN: 200
    PGBOUNCER_DEFAULT_POOL_SIZE: 20
  ports:
    - "5433:5432"
  depends_on:
    postgres:
      condition: service_healthy
  networks:
    - forge-net
  healthcheck:
    # pg_isready não existe na imagem bitnami/pgbouncer — usar psql via variável de ambiente
    test: ["CMD-SHELL", "psql postgresql://${POSTGRES_USER:-forge}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRESQL_DATABASE:-forge} -c 'SELECT 1' -q --no-align -t | grep -q 1"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 10s
```

**Atualizar `.env.example`:**

```bash
PGBOUNCER_PORT=5433
```

**Testes:**

```bash
uv run python -c "
import asyncio, psycopg
async def q():
    async with await psycopg.AsyncConnection.connect(
        'postgresql://forge:forge@localhost:5433/forge'
    ) as conn:
        await conn.execute('SELECT 1')
asyncio.run(asyncio.gather(*[q() for _ in range(50)]))
print('50 conexoes OK via PgBouncer')
"
```

---

### Passo 2.5 — Prometheus + Grafana

**Contexto:** Sem metricas nao ha como detectar degradacao antes que vire incidente.

**Mudanca em `apps/api/src/api/main.py`:**

```python
from prometheus_fastapi_instrumentator import Instrumentator

@asynccontextmanager
async def lifespan(app: FastAPI):
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    yield
```

**Criar `monitoring/prometheus.yml`:**

```yaml
scrape_configs:
  - job_name: fhir-forge-api
    static_configs:
      - targets: ["api:8000"]
    metrics_path: /metrics
    scrape_interval: 15s

  - job_name: redis
    static_configs:
      - targets: ["redis-exporter:9121"]   # depende do serviço abaixo
    scrape_interval: 15s
```

**Criar `monitoring/grafana/provisioning/datasources/prometheus.yml`** (necessário para Grafana descobrir o Prometheus automaticamente):

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

**Adicionar ao `docker-compose.yml`** (profile `monitoring`):

```yaml
redis-exporter:
  image: oliver006/redis_exporter:v1.63.0
  profiles: ["monitoring"]
  environment:
    REDIS_ADDR: redis://redis:6379
  ports: ["9121:9121"]
  depends_on: [redis]
  networks: [forge-net]

prometheus:
  image: prom/prometheus:v3.0.0
  profiles: ["monitoring"]
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
  ports: ["9090:9090"]
  depends_on: [redis-exporter]
  networks: [forge-net]

grafana:
  image: grafana/grafana:11.0.0
  profiles: ["monitoring"]
  environment:
    GF_SECURITY_ADMIN_PASSWORD: forge_dev
  ports: ["3001:3000"]
  volumes:
    - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
    - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards
  depends_on: [prometheus]
  networks: [forge-net]
```

**Dashboards a criar em `monitoring/grafana/dashboards/`:**

1. `api-throughput.json` — req/s, p50/p95 latência por endpoint
2. `queue-depth.json` — `llen fhir` do Redis (Dramatiq queue depth)
3. `cache-ratio.json` — hits/misses Redis (TermMapper cache)

**Testes:**

```bash
docker compose --profile monitoring up -d
curl -s http://localhost:8000/metrics | grep http_requests_total
curl -s http://localhost:9090/api/v1/targets | python -m json.tool | grep '"health":"up"'
```

---

### Passo 2.6 — docker-compose.prod.yml

**Criar `docker-compose.prod.yml`:**

```yaml
# Sem "version:" — chave depreciada em Docker Compose >= 2.0 (ignorada com aviso)

services:
  postgres:
    restart: always
    volumes:
      - postgres-data-prod:/var/lib/postgresql/data   # volume externo — não apagado em 'down'

  redis:
    restart: always

  hapi:
    restart: always

  snowstorm:
    restart: always

  langfuse:
    restart: always

  api:
    restart: always
    image: fhir-forge-api:${IMAGE_TAG:-latest}   # imagem produção, não build local
    environment:
      ENV: production
      LOG_LEVEL: INFO
      FEATURE_ADMIN_NOAUTH: "false"              # auth obrigatória em produção

  worker:
    restart: always
    image: fhir-forge-worker:${IMAGE_TAG:-latest}

volumes:
  postgres-data-prod:
    external: true   # deve existir previamente: docker volume create postgres-data-prod
```

---

### Gate de Saida da Fase 2 (binario)

```bash
# Stack completa healthy
docker compose up -d && make health
docker compose ps   # todos healthy/running

# Limites de memoria visiveis
docker stats --no-stream --format "table {{.Name}}\t{{.MemLimit}}" | grep -v "0B"

# TLS via Nginx
curl -k https://localhost/health   # 200

# Metricas
docker compose --profile monitoring up -d
curl -s http://localhost:8000/metrics | grep -q http_requests_total && echo "Metrics: OK"

# PgBouncer
uv run python -c "
import asyncio, psycopg
async def q():
    async with await psycopg.AsyncConnection.connect('postgresql://forge:forge@localhost:5433/forge') as c:
        await c.execute('SELECT 1')
asyncio.run(asyncio.gather(*[q() for _ in range(50)]))
print('PgBouncer: OK')
"

# Testes nao regridem
uv run pytest -m unit && uv run pytest -m e2e
```

**Gate verde** = todos os comandos saem com codigo 0.

---

## FASE 3 — Kubernetes (1–2 semanas)

Prerequisito: Gate Fase 2 verde + imagens publicadas num registry (ECR, GCR ou Docker Hub).

---

### Passo 3.1 — Helm Chart base

**Criar `helm/fhir-forge/`:**

```
helm/fhir-forge/
├── Chart.yaml                    # versao, appVersion: "2.0.0"
├── values.yaml                   # defaults dev (1 replica, recursos minimos)
├── values.prod.yaml              # prod (HPA, recursos maiores, TLS real)
└── templates/
    ├── _helpers.tpl
    ├── deployment-api.yaml       # FastAPI — 2 replicas base
    ├── deployment-worker.yaml    # Dramatiq — 1 replica base
    ├── statefulset-postgres.yaml # PVC 50Gi + PodDisruptionBudget
    ├── statefulset-redis.yaml    # Redis Sentinel: 1 master + 2 replicas
    ├── statefulset-hapi.yaml     # 1 pod + PVC 20Gi
    ├── statefulset-es.yaml       # 3 pods + PVC 100Gi cada
    ├── deployment-snowstorm.yaml
    ├── deployment-langfuse.yaml
    ├── ingress.yaml              # nginx-ingress + cert-manager (Let's Encrypt)
    ├── hpa-api.yaml              # CPU > 70%: scale 2->10
    ├── hpa-worker.yaml           # queue depth > 20: scale 1->5
    ├── configmap.yaml
    ├── externalsecret.yaml       # External Secrets Operator -> AWS Secrets Manager
    └── servicemonitor.yaml       # Prometheus Operator scrape
```

**`values.yaml` estrutura:**

```yaml
image:
  repository: your-ecr/fhir-forge
  tag: "2.0.0"
  pullPolicy: IfNotPresent

api:
  replicas: 2
  resources:
    requests: { cpu: "250m", memory: "512Mi" }
    limits:   { cpu: "1000m", memory: "1Gi" }

worker:
  replicas: 1
  resources:
    requests: { cpu: "500m", memory: "1Gi" }
    limits:   { cpu: "2000m", memory: "2Gi" }

hpa:
  api:
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
  worker:
    minReplicas: 1
    maxReplicas: 5
    targetQueueDepth: 20   # custom metric via Prometheus Adapter
```

---

### Passo 3.2 — GitHub Actions CI/CD

**Criar `.github/workflows/ci.yml`:**

```yaml
name: CI

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv run ruff check .
      - run: uv run mypy packages apps

  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras --dev
      - run: uv run pytest -m unit --cov=packages --cov-fail-under=85

  integration:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras --dev
      - run: uv run pytest -m integration

  build-and-deploy:
    if: github.ref == 'refs/heads/main'
    needs: [lint, unit, integration]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and push images
        run: |
          docker build -t $ECR_REGISTRY/fhir-forge-api:$GITHUB_SHA    -f apps/api/Dockerfile .
          docker build -t $ECR_REGISTRY/fhir-forge-worker:$GITHUB_SHA -f apps/worker/Dockerfile .
          docker push $ECR_REGISTRY/fhir-forge-api:$GITHUB_SHA
          docker push $ECR_REGISTRY/fhir-forge-worker:$GITHUB_SHA
      - name: Helm upgrade
        run: |
          helm upgrade --install fhir-forge helm/fhir-forge \
            --set image.tag=$GITHUB_SHA \
            -f helm/fhir-forge/values.prod.yaml \
            --namespace fhir-forge
```

---

### Gate de Saida da Fase 3 (binario)

```bash
# Helm valido
helm lint helm/fhir-forge
helm template fhir-forge helm/fhir-forge -f values.prod.yaml | kubectl apply --dry-run=client -f -

# Pods healthy
kubectl get pods -n fhir-forge     # todos Running
kubectl get hpa   -n fhir-forge    # TARGETS preenchidos (nao <unknown>)

# Scale-out funcional
kubectl run load-test --image=alpine --restart=Never -- \
    sh -c "for i in $(seq 1 100); do wget -q -O- http://api/convert & done; wait"
watch kubectl get hpa -n fhir-forge  # REPLICAS deve subir acima de 2

# E2E contra cluster
HAPI_BASE=https://$(kubectl get ingress -n fhir-forge -o jsonpath='{.items[0].spec.rules[0].host}')/fhir \
    uv run pytest -m e2e
```

**Gate verde** = todos os comandos saem com codigo 0 + HPA demonstrou scale-out.

---

## Resumo dos Arquivos Criticos

| Fase | Arquivo | Acao |
|---|---|---|
| 1.1 | `packages/connectors/src/connectors/hapi_client.py` | Pool httpx no `__init__` + `aclose()` |
| 1.1 | `packages/connectors/src/connectors/rnds_client.py` | Pool + cachear SSLContext |
| 1.1 | `packages/term_mapper/src/term_mapper/snowstorm_client.py` | Pool httpx |
| 1.1 | `packages/term_mapper/src/term_mapper/hapi_valueset_client.py` | Pool httpx |
| 1.2 | `packages/connectors/src/connectors/resilience.py` | Remover AsyncCircuitBreaker; aplicar decorators |
| 1.3 | `packages/core/src/core/llm_router.py` | Singleton + fallback chain real |
| 1.4 | `packages/fhir_forge/src/fhir_forge/service.py` | AsyncPostgresSaver como padrao |
| 1.1 | `packages/fhir_forge/src/fhir_forge/nodes/validation_node.py` | Pool httpx: AsyncClient por recurso → client compartilhado via parâmetro |
| 1.4 | `packages/fhir_forge/src/fhir_forge/nodes/mapping_node.py` | asyncio.gather paralelo (op_ids são strings — usar endpoint_map) |
| 1.4 | `packages/fhir_forge/src/fhir_forge/nodes/validation_node.py` | asyncio.gather paralelo (após refactor 1.1) |
| 1.4 | `packages/fhir_forge/src/fhir_forge/nodes/fix_node.py` | asyncio.gather paralelo |
| 1.5 | `packages/fhir_forge/src/fhir_forge/nodes/mapping_node.py` | wait_for 60s em `_map_endpoint()` (não no nó) |
| 1.5 | `packages/fhir_forge/src/fhir_forge/nodes/fix_node.py` | wait_for 60s em `_fix_resource()` (não no nó) |
| 1.6 | `apps/worker/src/worker/main.py` | Wire worker_concurrency |
| 1.6 | `Makefile` | Atualizar target `worker` |
| 1.7 | `apps/api/src/api/main.py` | slowapi rate limit + CORS explicito + /metrics |
| 1.7 | `packages/core/src/core/settings.py` | Adicionar `cors_allowed_origins` |
| 1.7 | `pyproject.toml` root | Adicionar slowapi + prometheus-fastapi-instrumentator |
| 1.8 | `packages/connectors/src/connectors/rnds_client.py` | Token RNDS em Redis |
| 1.9 | `apps/api/Dockerfile` (criar) | Multi-stage Python 3.12 |
| 1.9 | `apps/worker/Dockerfile` (criar) | Multi-stage Python 3.12 |
| 2.1 | `docker-compose.yml` | `deploy.resources.limits` em todos |
| 2.2 | `docker-compose.yml` | Healthcheck Langfuse |
| 2.3 | `nginx/nginx.conf` (criar) | Reverse proxy TLS + gzip + rate limit |
| 2.3 | `nginx/gen-certs.sh` (criar) | Script certificado self-signed dev |
| 2.4 | `docker-compose.yml` | Servico PgBouncer |
| 2.5 | `monitoring/prometheus.yml` (criar) | Scrape config |
| 2.5 | `docker-compose.yml` | Prometheus + Grafana (profile monitoring) |
| 2.6 | `docker-compose.prod.yml` (criar) | Override producao |
| 3 | `helm/fhir-forge/` (criar) | Helm chart completo |
| 3 | `.github/workflows/ci.yml` (criar) | CI/CD |

---

## Utilitarios Reutilizaveis (nao reescrever)

| Utilitário | Arquivo | Estado |
|---|---|---|
| `retry_async()` | `connectors/resilience.py:24` | Definido — nunca aplicado nos clientes HTTP |
| `fhir_circuit_breaker` | `connectors/resilience.py:17` | Definido — nunca aplicado; usar com `call_async()` |
| `AsyncCircuitBreaker` | `connectors/resilience.py:47-74` | **REMOVER** — antipattern com asyncio.run em executor |
| `breaker.call_async()` | pybreaker API pública | Disponível em pybreaker >= 0.7; substitui AsyncCircuitBreaker |
| `TermCache` | `term_mapper/cache.py:17` | OK — reaproveitar padrão para token RNDS |
| `settings.worker_concurrency` | `core/settings.py` | Definido — nunca lido pelo Dramatiq |
| `AsyncPostgresSaver` | dep instalada | Importável — não usada como default; usar com `async with` |

---

## Ordem de Execucao (ROI decrescente)

| # | Passo | ROI | Esforco estimado |
|---|---|---|---|
| 1 | 1.1 — Connection pool httpx | **Alto** — elimina N conexoes TCP por request | 2h |
| 2 | 1.4a — asyncio.gather LangGraph | **Alto** — latencia cai proporcionalmente ao n de endpoints | 1h |
| 3 | 1.2 — Ativar circuit breaker + retry | **Alto** — codigo ja existe, so faltam os decorators | 1h |
| 4 | 2.1 — Limites memoria docker-compose | **Alto** — evita OOM cascata, custo zero de codigo | 30min |
| 5 | 1.7 — Rate limiting + CORS | **Medio** — seguranca basica para ambiente compartilhado | 2h |
| 6 | 1.3 — LLM singleton + fallback | **Medio** — elimina recriacao de cliente | 2h |
| 7 | 1.5 — Timeout LangGraph | **Medio** — evita workers pendurados | 1h |
| 8 | 1.6 — Fiar worker_concurrency | **Medio** — escala horizontal sem custo | 1h |
| 9 | 1.4b — AsyncPostgresSaver | **Medio** — persistencia real em falhas | 1h |
| 10 | 2.3 — Nginx | **Medio** — TLS + gzip | 3h |
| 11 | 2.4 — PgBouncer | **Medio** — necessario acima de 4 workers | 1h |
| 12 | 2.5 — Prometheus + Grafana | **Medio** — observabilidade proativa | 3h |
| 13 | 1.8 — RNDS token Redis | **Baixo** — relevante quando RNDS em uso ativo | 1h |
| 14 | 1.9 — Dockerfiles | **Baixo** — prerequisito para Fase 2/3 | 2h |
| 15 | 3 — Helm + CI/CD | **Alto a longo prazo** — caminho para nuvem | 2 semanas |
