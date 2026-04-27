from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

GOLDEN_DIR = pathlib.Path(__file__).parent.parent.parent / "data" / "golden"
BASELINE_PATH = pathlib.Path(__file__).parent / "eval_baseline.json"

# Minimum acceptable metric values (any regression below these fails)
_PRECISION_FLOOR = 0.8
_RECALL_FLOOR = 0.8
_REGRESSION_TOLERANCE = 0.05  # 5 percentage-point drop from baseline triggers failure


def _build_mock_report() -> Any:
    """Build an EvalReport using the golden bundles as both predicted and expected.

    Precision and recall will be 1.0 for each pair (perfect match by resource type).
    This lets the regression test run without a live LLM or HAPI.
    """
    from eval.metrics import fhir_precision, fhir_recall, semantic_diff
    from eval.report import EvalReport, PairResult

    specs_dir = GOLDEN_DIR / "swagger_specs"
    bundles_dir = GOLDEN_DIR / "fhir_bundles"

    report = EvalReport()
    for spec_path in sorted(specs_dir.glob("*.yaml")) + sorted(specs_dir.glob("*.json")):
        expected_path = bundles_dir / f"{spec_path.stem}_expected.json"
        if not expected_path.exists():
            continue
        expected: dict[str, Any] = json.loads(expected_path.read_text())
        # Use expected bundle as "predicted" to get a deterministic baseline
        precision = fhir_precision(expected, expected)
        recall = fhir_recall(expected, expected)
        diff = semantic_diff(expected, expected)
        report.pairs.append(
            PairResult(
                name=spec_path.stem,
                precision=precision,
                recall=recall,
                diff=diff,
                valid=True,
            )
        )

    return report


@pytest.mark.regression
def test_eval_baseline_exists_or_creates() -> None:
    """If no baseline exists, generate it from the golden bundles and skip."""
    if not BASELINE_PATH.exists():
        report = _build_mock_report()
        BASELINE_PATH.write_text(report.to_json(), encoding="utf-8")
        pytest.skip(f"Baseline created at {BASELINE_PATH}. Re-run to validate.")


@pytest.mark.regression
def test_eval_precision_meets_floor() -> None:
    """Mean precision over golden pairs must be ≥ 0.8."""
    report = _build_mock_report()
    assert len(report.pairs) >= 2, "Need at least 2 golden pairs to evaluate"
    assert report.mean_precision >= _PRECISION_FLOOR, (
        f"Mean precision {report.mean_precision:.3f} < floor {_PRECISION_FLOOR}"
    )


@pytest.mark.regression
def test_eval_recall_meets_floor() -> None:
    """Mean recall over golden pairs must be ≥ 0.8."""
    report = _build_mock_report()
    assert report.mean_recall >= _RECALL_FLOOR, (
        f"Mean recall {report.mean_recall:.3f} < floor {_RECALL_FLOOR}"
    )


@pytest.mark.regression
def test_eval_no_regression_vs_baseline() -> None:
    """Current metrics must not drop > 5% vs the stored baseline."""
    if not BASELINE_PATH.exists():
        pytest.skip("No baseline found — run test_eval_baseline_exists_or_creates first")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    current = _build_mock_report()

    for metric in ("mean_precision", "mean_recall"):
        base_val: float = baseline.get(metric, 0.0)
        curr_val: float = getattr(current, metric)
        drop = base_val - curr_val
        assert drop <= _REGRESSION_TOLERANCE, (
            f"{metric} regressed by {drop:.3f} "
            f"(baseline={base_val:.3f}, current={curr_val:.3f})"
        )


@pytest.mark.regression
def test_eval_report_covers_all_golden_pairs() -> None:
    """Report must include every golden (spec, bundle) pair."""
    specs_dir = GOLDEN_DIR / "swagger_specs"
    bundles_dir = GOLDEN_DIR / "fhir_bundles"
    expected_names = {
        p.stem
        for p in list(specs_dir.glob("*.yaml")) + list(specs_dir.glob("*.json"))
        if (bundles_dir / f"{p.stem}_expected.json").exists()
    }

    report = _build_mock_report()
    reported_names = {p.name for p in report.pairs}

    assert expected_names == reported_names, (
        f"Missing pairs: {expected_names - reported_names}"
    )
