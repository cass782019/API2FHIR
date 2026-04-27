from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_redis(get_return: bytes | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=get_return)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    return redis


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_miss_returns_none() -> None:
    from term_mapper.cache import TermCache

    cache = TermCache(_make_redis(get_return=None))
    result = await cache.get("http://snomed.info/sct", "73211009")
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_hit_returns_coding() -> None:
    from term_mapper.cache import TermCache

    coding_json = json.dumps({"system": "http://snomed.info/sct", "code": "73211009", "display": "Diabetes mellitus"})
    redis = _make_redis(get_return=coding_json.encode())
    cache = TermCache(redis)
    result = await cache.get("http://snomed.info/sct", "73211009")
    assert result is not None
    assert result.code == "73211009"
    assert result.display == "Diabetes mellitus"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_set_calls_redis_set() -> None:
    from term_mapper.cache import TermCache
    from term_mapper.models import Coding

    redis = _make_redis()
    cache = TermCache(redis, default_ttl=600)
    coding = Coding(system="http://snomed.info/sct", code="73211009", display="Diabetes mellitus")
    await cache.set("http://snomed.info/sct", "73211009", coding)
    redis.set.assert_awaited_once()
    call_kwargs = redis.set.call_args
    assert call_kwargs.kwargs["ex"] == 600


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_set_custom_ttl() -> None:
    from term_mapper.cache import TermCache
    from term_mapper.models import Coding

    redis = _make_redis()
    cache = TermCache(redis, default_ttl=3600)
    coding = Coding(system="http://loinc.org", code="2093-3")
    await cache.set("http://loinc.org", "2093-3", coding, ttl=120)
    call_kwargs = redis.set.call_args
    assert call_kwargs.kwargs["ex"] == 120


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_delete_calls_redis_delete() -> None:
    from term_mapper.cache import TermCache

    redis = _make_redis()
    cache = TermCache(redis)
    await cache.delete("http://snomed.info/sct", "73211009")
    redis.delete.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_corrupted_json_returns_none() -> None:
    from term_mapper.cache import TermCache

    redis = _make_redis(get_return=b"not valid json{")
    cache = TermCache(redis)
    result = await cache.get("http://snomed.info/sct", "73211009")
    assert result is None


@pytest.mark.unit
def test_cache_key_is_deterministic() -> None:
    from term_mapper.cache import _cache_key

    k1 = _cache_key("http://snomed.info/sct", "73211009")
    k2 = _cache_key("http://snomed.info/sct", "73211009")
    assert k1 == k2
    assert k1.startswith("term_mapper:")


@pytest.mark.unit
def test_coding_to_dict_round_trip() -> None:
    from term_mapper.models import Coding

    c = Coding(system="http://loinc.org", code="2093-3", display="Cholesterol")
    d = c.to_dict()
    c2 = Coding.from_dict(d)
    assert c2.system == c.system
    assert c2.code == c.code
    assert c2.display == c.display


@pytest.mark.unit
def test_coding_to_dict_omits_empty_display() -> None:
    from term_mapper.models import Coding

    c = Coding(system="http://loinc.org", code="2093-3")
    d = c.to_dict()
    assert "display" not in d
