from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from .cache import TermCache
    from .hapi_valueset_client import HapiValueSetClient
    from .models import Coding, ConceptMatch
    from .snowstorm_client import SnowstormClient

log = structlog.get_logger(__name__)


class TermMapper:
    """Orchestrates terminology lookups: cache → Snowstorm → HAPI fallback."""

    def __init__(
        self,
        cache: TermCache,
        snowstorm: SnowstormClient,
        hapi: HapiValueSetClient,
    ) -> None:
        self._cache = cache
        self._snowstorm = snowstorm
        self._hapi = hapi

    async def map_code(
        self,
        system: str,
        code: str,
        preferred_system: str | None = None,
    ) -> Coding | None:
        """Resolve *code* in *system*, optionally translating to *preferred_system*.

        Resolution order:
          1. Redis cache (instant)
          2. Snowstorm $translate (if preferred_system differs from system)
          3. HAPI $lookup as fallback
        """
        target_system = preferred_system or system

        # 1. Cache hit
        cached = await self._cache.get(system, code)
        if cached is not None:
            log.debug("term_mapper_cache_hit", system=system, code=code)
            return cached

        result: Coding | None = None

        # 2. Snowstorm translate (cross-system)
        if preferred_system and preferred_system != system:
            result = await self._snowstorm.translate(system, code, preferred_system)
            if result:
                log.debug("term_mapper_snowstorm_translate", system=system, code=code)
                await self._cache.set(system, code, result)
                return result

        # 3. HAPI $lookup (same system)
        result = await self._hapi.lookup(target_system, code)
        if result:
            log.debug("term_mapper_hapi_lookup", system=system, code=code)
            await self._cache.set(system, code, result)
            return result

        log.warning("term_mapper_not_found", system=system, code=code)
        return None

    async def search(
        self,
        term: str,
        ecl: str | None = None,
    ) -> list[ConceptMatch]:
        """Free-text search across Snowstorm for SNOMED concepts."""
        return await self._snowstorm.find_concept(term, ecl=ecl)

    async def expand_valueset(
        self,
        valueset_url: str,
        filter_text: str | None = None,
    ) -> list[Coding]:
        """Expand a FHIR ValueSet via HAPI."""
        return await self._hapi.expand(valueset_url, filter_text=filter_text)
