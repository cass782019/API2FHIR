from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from .models import Coding


def _cache_key(system: str, code: str) -> str:
    safe_system = system.replace(":", "_").replace("/", "_")
    return f"term_mapper:{safe_system}:{code}"


class TermCache:
    """Redis-backed cache for resolved FHIR Codings."""

    def __init__(self, client: aioredis.Redis, default_ttl: int = 3600) -> None:
        self._redis = client
        self._default_ttl = default_ttl

    async def get(self, system: str, code: str) -> Coding | None:
        key = _cache_key(system, code)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            data: dict[str, str] = json.loads(raw)
            return Coding.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    async def set(self, system: str, code: str, coding: Coding, ttl: int | None = None) -> None:
        key = _cache_key(system, code)
        payload = json.dumps(coding.to_dict())
        effective_ttl = ttl if ttl is not None else self._default_ttl
        await self._redis.set(key, payload, ex=effective_ttl)

    async def delete(self, system: str, code: str) -> None:
        key = _cache_key(system, code)
        await self._redis.delete(key)
