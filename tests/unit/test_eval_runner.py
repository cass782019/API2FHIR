from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    import pathlib

_BUNDLE_PATIENT = {
    "resourceType": "Bundle",
    "id": "b1",
    "type": "collection",
    "entry": [{"resource": {"resourceType": "Patient", "id": "p1"}}],
}
_BUNDLE_OBS = {
    "resourceType": "Bundle",
    "id": "b2",
    "type": "collection",
    "entry": [{"resource": {"resourceType": "Observation", "id": "o1"}}],
}


@pytest.fixture
def golden_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    specs = tmp_path / "swagger_specs"
    bundles = tmp_path / "fhir_bundles"
    specs.mkdir()
    bundles.mkdir()

    # Create two fake golden pairs
    for name in ("api_a", "api_b"):
        (specs / f"{name}.yaml").write_text("openapi: '3.0.0'\ninfo:\n  title: T\n  version: v1\npaths: {}")
        (bundles / f"{name}_expected.json").write_text(json.dumps(_BUNDLE_PATIENT))

    return tmp_path


@pytest.mark.unit
def test_runner_processes_all_pairs(golden_dir: pathlib.Path) -> None:
    mock_client = MagicMock()

    with (
        patch("eval.runner._convert_pair", new=AsyncMock(return_value=_BUNDLE_PATIENT)),
        patch.object(
            __import__("eval.runner", fromlist=["EvalRunner"]).EvalRunner,
            "_validate",
            new=AsyncMock(return_value=True),
        ),
    ):
        from eval.runner import EvalRunner

        runner = EvalRunner(hapi_base_url="http://hapi.test/fhir", client=mock_client)
        report = runner.run(golden_dir)

    assert len(report.pairs) == 2
    assert {p.name for p in report.pairs} == {"api_a", "api_b"}


@pytest.mark.unit
def test_runner_precision_recall_perfect_match(golden_dir: pathlib.Path) -> None:
    mock_client = MagicMock()

    with (
        patch("eval.runner._convert_pair", new=AsyncMock(return_value=_BUNDLE_PATIENT)),
        patch("eval.runner.EvalRunner._validate", new=AsyncMock(return_value=True)),
    ):
        from eval.runner import EvalRunner

        runner = EvalRunner(client=mock_client)
        report = runner.run(golden_dir)

    for pair in report.pairs:
        assert pair.precision == 1.0
        assert pair.recall == 1.0


@pytest.mark.unit
def test_runner_records_error_on_conversion_failure(golden_dir: pathlib.Path) -> None:
    mock_client = MagicMock()

    with (
        patch("eval.runner._convert_pair", new=AsyncMock(side_effect=RuntimeError("LLM down"))),
        patch("eval.runner.EvalRunner._validate", new=AsyncMock(return_value=False)),
    ):
        from eval.runner import EvalRunner

        runner = EvalRunner(client=mock_client)
        report = runner.run(golden_dir)

    assert len(report.pairs) == 2
    for pair in report.pairs:
        assert pair.error != ""
        assert pair.precision == 0.0


@pytest.mark.unit
def test_runner_skips_spec_with_no_bundle(tmp_path: pathlib.Path) -> None:
    specs = tmp_path / "swagger_specs"
    bundles = tmp_path / "fhir_bundles"
    specs.mkdir()
    bundles.mkdir()
    (specs / "orphan.yaml").write_text("openapi: '3.0.0'\ninfo:\n  title: T\n  version: v1\npaths: {}")
    # no matching bundle

    mock_client = MagicMock()

    with patch("eval.runner._convert_pair", new=AsyncMock(return_value=_BUNDLE_PATIENT)):
        from eval.runner import EvalRunner

        runner = EvalRunner(client=mock_client)
        report = runner.run(tmp_path)

    assert report.pairs == []


@pytest.mark.unit
def test_validate_returns_true_on_no_errors() -> None:
    from eval.runner import EvalRunner

    runner = EvalRunner()
    outcome = {"issue": [{"severity": "information", "code": "informational"}]}

    with patch("httpx.AsyncClient") as mock_ctx:
        mock_resp = MagicMock()
        mock_resp.json.return_value = outcome
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        import asyncio
        result = asyncio.run(runner._validate(_BUNDLE_PATIENT))

    assert result is True


@pytest.mark.unit
def test_validate_returns_false_on_error_issue() -> None:
    from eval.runner import EvalRunner

    runner = EvalRunner()
    outcome = {"issue": [{"severity": "error", "code": "invalid"}]}

    with patch("httpx.AsyncClient") as mock_ctx:
        mock_resp = MagicMock()
        mock_resp.json.return_value = outcome
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        import asyncio
        result = asyncio.run(runner._validate(_BUNDLE_PATIENT))

    assert result is False


@pytest.mark.unit
def test_validate_returns_false_on_exception() -> None:
    from eval.runner import EvalRunner

    runner = EvalRunner()

    with patch("httpx.AsyncClient", side_effect=OSError("conn refused")):
        import asyncio
        result = asyncio.run(runner._validate(_BUNDLE_PATIENT))

    assert result is False


@pytest.mark.unit
def test_runner_get_client_uses_injected(tmp_path: pathlib.Path) -> None:
    mock_client = MagicMock()

    from eval.runner import EvalRunner

    runner = EvalRunner(client=mock_client)
    assert runner._get_client() is mock_client


@pytest.mark.unit
def test_report_print_summary(capsys: pytest.CaptureFixture[str]) -> None:
    from eval.report import EvalReport, PairResult
    from rich.console import Console

    report = EvalReport(
        pairs=[
            PairResult(name="api_a", precision=1.0, recall=1.0, diff={}, valid=True),
            PairResult(name="api_b", precision=0.5, recall=0.5, diff={"changed": {}}, valid=False),
        ]
    )
    console = Console(highlight=False, markup=True)
    # should not raise
    report.print_summary(console)


@pytest.mark.unit
def test_eval_report_empty_pairs() -> None:
    from eval.report import EvalReport

    report = EvalReport()
    assert report.mean_precision == 0.0
    assert report.mean_recall == 0.0
    assert report.mean_f1 == 0.0
    assert report.validation_rate == 0.0
    assert report.regression_free is True
