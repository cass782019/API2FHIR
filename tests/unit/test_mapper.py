from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_cache(hit: object = None) -> MagicMock:
    cache = MagicMock()
    cache.get = AsyncMock(return_value=hit)
    cache.set = AsyncMock(return_value=None)
    return cache


def _make_snowstorm(translate_return: object = None, find_return: list | None = None) -> MagicMock:
    snow = MagicMock()
    snow.translate = AsyncMock(return_value=translate_return)
    snow.find_concept = AsyncMock(return_value=find_return or [])
    return snow


def _make_hapi(lookup_return: object = None, expand_return: list | None = None) -> MagicMock:
    hapi = MagicMock()
    hapi.lookup = AsyncMock(return_value=lookup_return)
    hapi.expand = AsyncMock(return_value=expand_return or [])
    return hapi


_SNOMED = "http://snomed.info/sct"
_LOINC = "http://loinc.org"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_hit_returns_without_calling_snowstorm() -> None:
    from term_mapper.mapper import TermMapper
    from term_mapper.models import Coding

    hit = Coding(system=_SNOMED, code="73211009", display="Diabetes mellitus")
    cache = _make_cache(hit=hit)
    snow = _make_snowstorm()
    hapi = _make_hapi()

    mapper = TermMapper(cache, snow, hapi)
    result = await mapper.map_code(_SNOMED, "73211009")

    assert result is not None
    assert result.code == "73211009"
    snow.translate.assert_not_called()
    hapi.lookup.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_miss_calls_snowstorm_translate_cross_system() -> None:
    from term_mapper.mapper import TermMapper
    from term_mapper.models import Coding

    translated = Coding(system=_LOINC, code="2093-3", display="Cholesterol")
    cache = _make_cache(hit=None)
    snow = _make_snowstorm(translate_return=translated)
    hapi = _make_hapi()

    mapper = TermMapper(cache, snow, hapi)
    result = await mapper.map_code(_SNOMED, "73211009", preferred_system=_LOINC)

    assert result is not None
    assert result.code == "2093-3"
    snow.translate.assert_awaited_once_with(_SNOMED, "73211009", _LOINC)
    cache.set.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_snowstorm_miss_falls_back_to_hapi() -> None:
    from term_mapper.mapper import TermMapper
    from term_mapper.models import Coding

    hapi_result = Coding(system=_SNOMED, code="73211009", display="Diabetes mellitus (HAPI)")
    cache = _make_cache(hit=None)
    snow = _make_snowstorm(translate_return=None)
    hapi = _make_hapi(lookup_return=hapi_result)

    mapper = TermMapper(cache, snow, hapi)
    result = await mapper.map_code(_SNOMED, "73211009", preferred_system=_LOINC)

    assert result is not None
    assert "HAPI" in result.display
    hapi.lookup.assert_awaited_once()
    cache.set.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_all_sources_miss_returns_none() -> None:
    from term_mapper.mapper import TermMapper

    cache = _make_cache(hit=None)
    snow = _make_snowstorm(translate_return=None)
    hapi = _make_hapi(lookup_return=None)

    mapper = TermMapper(cache, snow, hapi)
    result = await mapper.map_code(_SNOMED, "99999999", preferred_system=_LOINC)

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_same_system_skips_translate() -> None:
    from term_mapper.mapper import TermMapper
    from term_mapper.models import Coding

    hapi_result = Coding(system=_SNOMED, code="73211009", display="Diabetes mellitus")
    cache = _make_cache(hit=None)
    snow = _make_snowstorm()
    hapi = _make_hapi(lookup_return=hapi_result)

    mapper = TermMapper(cache, snow, hapi)
    # same system for source and preferred → no translation needed
    result = await mapper.map_code(_SNOMED, "73211009", preferred_system=_SNOMED)

    snow.translate.assert_not_called()
    assert result is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_delegates_to_snowstorm() -> None:
    from term_mapper.mapper import TermMapper
    from term_mapper.models import Coding, ConceptMatch

    matches = [
        ConceptMatch(coding=Coding(_SNOMED, "38341003", "Hypertension"), score=1.0, source="snowstorm")
    ]
    cache = _make_cache()
    snow = _make_snowstorm(find_return=matches)
    hapi = _make_hapi()

    mapper = TermMapper(cache, snow, hapi)
    results = await mapper.search("hypertension", ecl="<404684003")

    assert len(results) == 1
    snow.find_concept.assert_awaited_once_with("hypertension", ecl="<404684003")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expand_valueset_delegates_to_hapi() -> None:
    from term_mapper.mapper import TermMapper
    from term_mapper.models import Coding

    codings = [Coding(_SNOMED, "73211009", "Diabetes mellitus")]
    cache = _make_cache()
    snow = _make_snowstorm()
    hapi = _make_hapi(expand_return=codings)

    mapper = TermMapper(cache, snow, hapi)
    results = await mapper.expand_valueset("http://hl7.org/fhir/ValueSet/condition-code")

    assert len(results) == 1
    hapi.expand.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_preferred_system_skips_translate_calls_hapi() -> None:
    from term_mapper.mapper import TermMapper
    from term_mapper.models import Coding

    hapi_result = Coding(system=_SNOMED, code="73211009", display="Diabetes mellitus")
    cache = _make_cache(hit=None)
    snow = _make_snowstorm()
    hapi = _make_hapi(lookup_return=hapi_result)

    mapper = TermMapper(cache, snow, hapi)
    result = await mapper.map_code(_SNOMED, "73211009")  # no preferred_system

    snow.translate.assert_not_called()
    hapi.lookup.assert_awaited_once()
    assert result is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_set_after_hapi_lookup() -> None:
    from term_mapper.mapper import TermMapper
    from term_mapper.models import Coding

    hapi_result = Coding(system=_SNOMED, code="73211009")
    cache = _make_cache(hit=None)
    hapi = _make_hapi(lookup_return=hapi_result)

    mapper = TermMapper(cache, _make_snowstorm(), hapi)
    await mapper.map_code(_SNOMED, "73211009")

    cache.set.assert_awaited_once_with(_SNOMED, "73211009", hapi_result)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hapi_expand_with_filter() -> None:
    from term_mapper.mapper import TermMapper

    cache = _make_cache()
    hapi = _make_hapi(expand_return=[])
    mapper = TermMapper(cache, _make_snowstorm(), hapi)
    await mapper.expand_valueset("http://hl7.org/fhir/ValueSet/condition-code", filter_text="diab")

    hapi.expand.assert_awaited_once_with(
        "http://hl7.org/fhir/ValueSet/condition-code", filter_text="diab"
    )
