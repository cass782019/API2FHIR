"""ProxyLLM — proxy local que expõe /v1/messages no formato Anthropic.

Backends (em ordem de prioridade):
  1. Ollama   — http://ollama:11434  (se OLLAMA_URL estiver acessível)
  2. Mock     — retorna FHIR realista sem I/O externo

Uso:
    uv run python proxyllm/server.py           # porta 9099
    PROXYLLM_PORT=9090 uv run python proxyllm/server.py

Configurar no .env para que o pipeline use este proxy:
    ANTHROPIC_BASE_URL=http://localhost:9099
    ANTHROPIC_API_KEY=proxyllm-local
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("proxyllm")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
PORT = int(os.getenv("PROXYLLM_PORT", "9099"))

app = FastAPI(title="ProxyLLM", version="0.1.0")


# ─── helpers ──────────────────────────────────────────────────────────────────

def _build_response(text: str, model: str = "proxyllm-mock") -> dict[str, Any]:
    return {
        "id": f"msg_{uuid.uuid4().hex[:16]}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 256,
            "output_tokens": len(text) // 4,
        },
    }


async def _ollama_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def _messages_to_prompt(messages: list[dict[str, Any]], system: str) -> str:
    parts: list[str] = []
    if system:
        parts.append(f"System: {system}\n")
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"
            )
        parts.append(f"{role.capitalize()}: {content}")
    parts.append("Assistant:")
    return "\n".join(parts)


async def _call_ollama(prompt: str, max_tokens: int) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",  # Request JSON output when the model supports it
        "options": {"num_predict": min(max_tokens, 1024)},
    }
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(f"{OLLAMA_URL}/api/generate", json=payload)
        r.raise_for_status()
        return r.json().get("response", "")


def _extract_json_text(text: str) -> str:
    """Extract the first valid JSON object from an LLM response string.

    Strategy:
      1. Direct json.loads (model returned clean JSON)
      2. json.JSONDecoder.raw_decode — finds the first '{' and parses forward
      3. Greedy regex fallback for malformed but recoverable responses
    """
    # 1. Direct parse
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # 2. Find first '{' and use raw_decode (handles leading whitespace/text)
    start = text.find("{")
    if start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text, start)
            return json.dumps(obj, ensure_ascii=False)
        except json.JSONDecodeError:
            pass

    # 3. Greedy regex — last resort
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)

    return text  # return as-is; caller will surface the raw text


# ─── mock FHIR ────────────────────────────────────────────────────────────────
# Limitação conhecida (aceito para dev): _FHIR_MOCKS é um conjunto estático de
# recursos FHIR pré-gerados. Os IDs são gerados uma única vez na inicialização
# do módulo (não por requisição), então requisições repetidas ao mesmo tipo
# retornam o mesmo id base. Isso é intencional para simplicidade — em produção
# o backend real (Ollama ou Anthropic) gera recursos dinâmicos.
# Para testes de integração use ANTHROPIC_BASE_URL apontando para o Anthropic real.

_FHIR_MOCKS: dict[str, dict[str, Any]] = {
    "patient": {
        "resourceType": "Patient",
        "id": f"mock-patient-{uuid.uuid4().hex[:8]}",
        "identifier": [
            {"system": "https://rnds.saude.gov.br/fhir/NamingSystem/cpf", "value": "123.456.789-09"},
            {"system": "https://rnds.saude.gov.br/fhir/NamingSystem/cns", "value": "700000000000001"},
        ],
        "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}],
        "gender": "female",
        "birthDate": "1985-03-15",
    },
    "encounter": {
        "resourceType": "Encounter",
        "id": f"mock-encounter-{uuid.uuid4().hex[:8]}",
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "AMB",
            "display": "ambulatory",
        },
        "subject": {"reference": "Patient/mock-patient-001"},
    },
    "observation": {
        "resourceType": "Observation",
        "id": f"mock-obs-{uuid.uuid4().hex[:8]}",
        "status": "final",
        "code": {
            "coding": [{"system": "http://loinc.org", "code": "29463-7", "display": "Body weight"}]
        },
        "subject": {"reference": "Patient/mock-patient-001"},
        "valueQuantity": {"value": 72.5, "unit": "kg", "system": "http://unitsofmeasure.org", "code": "kg"},
    },
    "medication": {
        "resourceType": "MedicationRequest",
        "id": f"mock-medreq-{uuid.uuid4().hex[:8]}",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.whocc.no/atc", "code": "M01AE01", "display": "Ibuprofen"}]
        },
        "subject": {"reference": "Patient/mock-patient-001"},
        "dosageInstruction": [{"text": "400mg every 8 hours"}],
    },
    "condition": {
        "resourceType": "Condition",
        "id": f"mock-cond-{uuid.uuid4().hex[:8]}",
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]
        },
        "code": {
            "coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "J06.9", "display": "Upper respiratory infection"}]
        },
        "subject": {"reference": "Patient/mock-patient-001"},
    },
}

_DEFAULT_MOCK = {
    "resourceType": "Basic",
    "id": f"mock-basic-{uuid.uuid4().hex[:8]}",
}


def _detect_resource_type(prompt_text: str) -> str:
    text = prompt_text.lower()
    for key in ("patient", "encounter", "observation", "medication", "condition"):
        if key in text:
            return key
    return "default"


def _mock_fhir_response(prompt_text: str) -> str:
    key = _detect_resource_type(prompt_text)
    resource = _FHIR_MOCKS.get(key, _DEFAULT_MOCK)
    # Regenera IDs para que cada chamada seja única
    resource = dict(resource)
    resource["id"] = f"mock-{resource['resourceType'].lower()}-{uuid.uuid4().hex[:8]}"
    return json.dumps(resource, ensure_ascii=False)


# ─── endpoint principal ───────────────────────────────────────────────────────

@app.post("/v1/messages")
async def messages(request: Request) -> JSONResponse:
    body: dict[str, Any] = await request.json()

    system: str = body.get("system", "")
    msgs: list[dict[str, Any]] = body.get("messages", [])
    max_tokens: int = body.get("max_tokens", 1024)

    # Constrói texto do prompt para detecção de resource
    prompt_text = _messages_to_prompt(msgs, system)

    if await _ollama_available():
        log.info("backend=ollama model=%s", OLLAMA_MODEL)
        try:
            text = await _call_ollama(prompt_text, max_tokens)
            text = _extract_json_text(text)
            return JSONResponse(_build_response(text, model=f"ollama/{OLLAMA_MODEL}"))
        except Exception as exc:
            log.warning("ollama_failed fallback=mock error=%s", exc)

    log.info("backend=mock resource=%s", _detect_resource_type(prompt_text))
    text = _mock_fhir_response(prompt_text)
    return JSONResponse(_build_response(text, model="proxyllm-mock"))


@app.get("/health")
async def health() -> dict[str, Any]:
    ollama_ok = await _ollama_available()
    return {
        "status": "ok",
        "backend": "ollama" if ollama_ok else "mock",
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL,
    }


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "ProxyLLM", "docs": "/docs", "health": "/health"}


if __name__ == "__main__":
    log.info("ProxyLLM iniciando na porta %s  (Ollama: %s)", PORT, OLLAMA_URL)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
