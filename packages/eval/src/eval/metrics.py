from __future__ import annotations

from typing import Any

from deepdiff import DeepDiff

_IGNORE_PATHS = {"id", "meta.lastUpdated", "meta.versionId", "meta.tag"}

_DEFAULT_EXCLUDE = [
    r"root\['id'\]",
    r"root\['meta'\]\['lastUpdated'\]",
    r"root\['meta'\]\['versionId'\]",
    r"root\['entry'\]\[\d+\]\['resource'\]\['id'\]",
    r"root\['entry'\]\[\d+\]\['resource'\]\['meta'\]",
    r"root\['entry'\]\[\d+\]\['fullUrl'\]",
]


def _extract_resource_types(bundle: dict[str, Any]) -> set[str]:
    """Collect all resourceType values from a Bundle's entries."""
    types: set[str] = set()
    if bundle.get("resourceType") != "Bundle":
        return {bundle.get("resourceType", "")}
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        rt = resource.get("resourceType")
        if rt:
            types.add(rt)
    return types


def _extract_coding_systems(bundle: dict[str, Any]) -> set[str]:
    """Collect all coding systems referenced in the bundle (best-effort)."""
    systems: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if "system" in node and "code" in node:
                systems.add(node["system"])
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(bundle)
    return systems


def fhir_precision(predicted: dict[str, Any], expected: dict[str, Any]) -> float:
    """Fraction of predicted resource types that appear in the expected bundle.

    Measures how many of the predicted resources are "correct" (present in ground truth).
    Returns 1.0 when predicted is empty (vacuously correct).
    """
    pred_types = _extract_resource_types(predicted)
    if not pred_types:
        return 1.0
    exp_types = _extract_resource_types(expected)
    matched = pred_types & exp_types
    return len(matched) / len(pred_types)


def fhir_recall(predicted: dict[str, Any], expected: dict[str, Any]) -> float:
    """Fraction of expected resource types that are present in the predicted bundle.

    Measures coverage: how many expected resources were generated.
    Returns 1.0 when expected is empty.
    """
    exp_types = _extract_resource_types(expected)
    if not exp_types:
        return 1.0
    pred_types = _extract_resource_types(predicted)
    matched = exp_types & pred_types
    return len(matched) / len(exp_types)


def semantic_diff(
    a: dict[str, Any],
    b: dict[str, Any],
    ignore_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Return a DeepDiff dict ignoring volatile FHIR fields (id, meta timestamps).

    Args:
        a: First bundle dict.
        b: Second bundle dict.
        ignore_paths: Additional regex patterns to exclude (merged with defaults).

    Returns:
        DeepDiff result as a plain dict; empty dict means no semantic difference.
    """
    exclude = list(_DEFAULT_EXCLUDE) + (ignore_paths or [])
    diff = DeepDiff(
        a,
        b,
        ignore_order=True,
        exclude_regex_paths=exclude,
    )
    return dict(diff)
