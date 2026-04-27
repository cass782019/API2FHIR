from __future__ import annotations

import pytest

_BUNDLE_A = {
    "resourceType": "Bundle",
    "id": "bundle-a",
    "type": "collection",
    "entry": [
        {"resource": {"resourceType": "Patient", "id": "p1"}},
        {"resource": {"resourceType": "Observation", "id": "o1"}},
        {"resource": {"resourceType": "Condition", "id": "c1"}},
    ],
}

_BUNDLE_B = {
    "resourceType": "Bundle",
    "id": "bundle-b",
    "type": "collection",
    "entry": [
        {"resource": {"resourceType": "Patient", "id": "p2"}},
        {"resource": {"resourceType": "Observation", "id": "o2"}},
        {"resource": {"resourceType": "Encounter", "id": "e1"}},
    ],
}

_BUNDLE_EMPTY = {"resourceType": "Bundle", "type": "collection", "entry": []}


@pytest.mark.unit
def test_precision_perfect_match() -> None:
    from eval.metrics import fhir_precision

    assert fhir_precision(_BUNDLE_A, _BUNDLE_A) == 1.0


@pytest.mark.unit
def test_precision_partial_overlap() -> None:
    from eval.metrics import fhir_precision

    # A has Patient, Observation, Condition; B has Patient, Observation, Encounter
    # predicted=A, expected=B → A∩B = {Patient, Observation} → 2/3
    result = fhir_precision(_BUNDLE_A, _BUNDLE_B)
    assert abs(result - 2 / 3) < 1e-9


@pytest.mark.unit
def test_precision_no_overlap() -> None:
    from eval.metrics import fhir_precision

    pred = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "MedicationRequest"}}],
    }
    expected = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "AllergyIntolerance"}}],
    }
    assert fhir_precision(pred, expected) == 0.0


@pytest.mark.unit
def test_precision_empty_predicted_returns_one() -> None:
    from eval.metrics import fhir_precision

    assert fhir_precision(_BUNDLE_EMPTY, _BUNDLE_A) == 1.0


@pytest.mark.unit
def test_recall_perfect_match() -> None:
    from eval.metrics import fhir_recall

    assert fhir_recall(_BUNDLE_A, _BUNDLE_A) == 1.0


@pytest.mark.unit
def test_recall_partial_overlap() -> None:
    from eval.metrics import fhir_recall

    # A has Patient, Observation, Condition; B has Patient, Observation, Encounter
    # predicted=A, expected=B → A∩B = {Patient, Observation} → 2/3
    result = fhir_recall(_BUNDLE_A, _BUNDLE_B)
    assert abs(result - 2 / 3) < 1e-9


@pytest.mark.unit
def test_recall_empty_expected_returns_one() -> None:
    from eval.metrics import fhir_recall

    assert fhir_recall(_BUNDLE_A, _BUNDLE_EMPTY) == 1.0


@pytest.mark.unit
def test_semantic_diff_identical_bundles_no_diff() -> None:
    from eval.metrics import semantic_diff

    diff = semantic_diff(_BUNDLE_A, _BUNDLE_A)
    assert diff == {}


@pytest.mark.unit
def test_semantic_diff_ignores_id_field() -> None:
    from eval.metrics import semantic_diff

    a = {"resourceType": "Bundle", "id": "bundle-1", "type": "collection", "entry": []}
    b = {"resourceType": "Bundle", "id": "bundle-2", "type": "collection", "entry": []}
    diff = semantic_diff(a, b)
    assert diff == {}


@pytest.mark.unit
def test_semantic_diff_ignores_meta_timestamps() -> None:
    from eval.metrics import semantic_diff

    a = {
        "resourceType": "Bundle",
        "id": "b1",
        "type": "collection",
        "meta": {"lastUpdated": "2024-01-01T00:00:00Z", "versionId": "1"},
        "entry": [],
    }
    b = {
        "resourceType": "Bundle",
        "id": "b2",
        "type": "collection",
        "meta": {"lastUpdated": "2025-06-01T12:00:00Z", "versionId": "99"},
        "entry": [],
    }
    diff = semantic_diff(a, b)
    assert diff == {}


@pytest.mark.unit
def test_semantic_diff_detects_type_change() -> None:
    from eval.metrics import semantic_diff

    a = {"resourceType": "Bundle", "type": "collection", "entry": []}
    b = {"resourceType": "Bundle", "type": "transaction", "entry": []}
    diff = semantic_diff(a, b)
    assert diff != {}


@pytest.mark.unit
def test_semantic_diff_custom_ignore_paths() -> None:
    from eval.metrics import semantic_diff

    a = {"resourceType": "Bundle", "type": "collection", "status": "active", "entry": []}
    b = {"resourceType": "Bundle", "type": "collection", "status": "inactive", "entry": []}
    diff_with = semantic_diff(a, b, ignore_paths=[r"root\['status'\]"])
    assert diff_with == {}
    diff_without = semantic_diff(a, b)
    assert diff_without != {}


@pytest.mark.unit
def test_pair_result_f1_score() -> None:
    from eval.report import PairResult

    pair = PairResult(name="test", precision=0.8, recall=0.6, diff={}, valid=True)
    expected_f1 = 2 * 0.8 * 0.6 / (0.8 + 0.6)
    assert abs(pair.f1 - expected_f1) < 1e-9


@pytest.mark.unit
def test_pair_result_passed_when_valid_and_no_diff() -> None:
    from eval.report import PairResult

    pair = PairResult(name="ok", precision=1.0, recall=1.0, diff={}, valid=True)
    assert pair.passed is True


@pytest.mark.unit
def test_pair_result_not_passed_when_has_diff() -> None:
    from eval.report import PairResult

    pair = PairResult(name="fail", precision=1.0, recall=1.0, diff={"values_changed": {}}, valid=True)
    assert pair.passed is False


@pytest.mark.unit
def test_eval_report_aggregates_metrics() -> None:
    from eval.report import EvalReport, PairResult

    report = EvalReport(
        pairs=[
            PairResult(name="a", precision=1.0, recall=1.0, diff={}, valid=True),
            PairResult(name="b", precision=0.6, recall=0.8, diff={}, valid=False),
        ]
    )
    assert abs(report.mean_precision - 0.8) < 1e-9
    assert abs(report.mean_recall - 0.9) < 1e-9
    assert report.validation_rate == 0.5


@pytest.mark.unit
def test_eval_report_to_json_is_valid() -> None:
    import json

    from eval.report import EvalReport, PairResult

    report = EvalReport(
        pairs=[PairResult(name="x", precision=0.9, recall=0.9, diff={}, valid=True)]
    )
    payload = json.loads(report.to_json())
    assert "mean_precision" in payload
    assert len(payload["pairs"]) == 1
