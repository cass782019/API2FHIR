from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

import structlog

from eval.metrics import fhir_precision, fhir_recall, semantic_diff
from eval.report import EvalReport, PairResult

if TYPE_CHECKING:
    from pathlib import Path

    import anthropic

log = structlog.get_logger(__name__)


def _load_bundle(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


async def _convert_pair(
    spec_path: Path,
    *,
    client: anthropic.AsyncAnthropic,
    hapi_base_url: str,
) -> dict[str, Any]:
    from fhir_forge.service import convert as fhir_convert
    from swagger_lens.parser import parse_spec

    spec_bytes = spec_path.read_bytes()  # noqa: ASYNC240
    swagger_spec = parse_spec(spec_bytes, fmt="auto")
    job_id = f"eval-{spec_path.stem}"
    return await fhir_convert(swagger_spec, job_id, client=client, hapi_base_url=hapi_base_url)


class EvalRunner:
    def __init__(
        self,
        *,
        hapi_base_url: str = "http://localhost:8090/fhir",
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._hapi_base_url = hapi_base_url
        self._client = client

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is not None:
            return self._client
        import anthropic as _anthropic
        from core.settings import settings

        return _anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )

    def run(self, golden_dir: Path) -> EvalReport:
        """Evaluate all spec/bundle pairs in golden_dir synchronously."""
        return asyncio.run(self.arun(golden_dir))

    async def arun(self, golden_dir: Path) -> EvalReport:
        """Evaluate all spec/bundle pairs in golden_dir."""
        specs_dir = golden_dir / "swagger_specs"
        bundles_dir = golden_dir / "fhir_bundles"

        report = EvalReport()
        client = self._get_client()

        spec_files = sorted(specs_dir.glob("*.yaml")) + sorted(specs_dir.glob("*.json"))

        for spec_path in spec_files:
            stem = spec_path.stem
            expected_path = bundles_dir / f"{stem}_expected.json"
            if not expected_path.exists():
                log.warning("no_expected_bundle", spec=stem)
                continue

            log.info("evaluating_pair", spec=stem)
            expected = _load_bundle(expected_path)

            t0 = time.perf_counter()
            try:
                predicted = await _convert_pair(
                    spec_path,
                    client=client,
                    hapi_base_url=self._hapi_base_url,
                )
                elapsed = time.perf_counter() - t0

                precision = fhir_precision(predicted, expected)
                recall = fhir_recall(predicted, expected)
                diff = semantic_diff(predicted, expected)
                valid = await self._validate(predicted)

                report.pairs.append(
                    PairResult(
                        name=stem,
                        precision=precision,
                        recall=recall,
                        diff=diff,
                        valid=valid,
                    )
                )
                log.info(
                    "pair_evaluated",
                    spec=stem,
                    precision=precision,
                    recall=recall,
                    elapsed=round(elapsed, 2),
                )
            except Exception as exc:
                log.error("pair_failed", spec=stem, error=str(exc))
                report.pairs.append(
                    PairResult(
                        name=stem,
                        precision=0.0,
                        recall=0.0,
                        diff={},
                        valid=False,
                        error=str(exc),
                    )
                )

        return report

    async def _validate(self, bundle: dict[str, Any]) -> bool:
        """POST the bundle to HAPI $validate; returns True if no errors."""
        import httpx

        url = f"{self._hapi_base_url}/Bundle/$validate"
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(url, json=bundle)
            outcome = resp.json()
            issues = outcome.get("issue", [])
            return not any(
                i.get("severity") in ("error", "fatal") for i in issues
            )
        except Exception as exc:
            log.warning("validate_failed", error=str(exc))
            return False
