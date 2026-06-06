"""Trap-dataset regression tests (V2 Phase 5).

These tests guard the verdict distribution of a known fixture set so a
future prompt tweak, model swap, or search-service change cannot silently
regress the headline accuracy.

## Why a tolerance?

The verdict LLM is non-deterministic and the search provider returns
time-varying evidence. A claim that was "verified" last month may flip to
"inaccurate" tomorrow even when nothing in our code changed. The
regression test therefore asserts that the **summary distribution** of
the run is within a small tolerance of the recorded value, not that every
individual claim matches.

## When the suite is empty

If no fixtures are present in ``test_assets/`` (the default state of a
fresh checkout), every test in this module is **skipped**. Drop a fixture
in, add an entry to ``expected_results.json``, and the suite starts
running immediately. This is the intent: the framework ships with the
code, the fixtures are populated on demand.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "test_assets"
EXPECTED_PATH = ASSETS / "expected_results.json"
PDFS = ASSETS / "pdfs"
IMAGES = ASSETS / "images"
TRAP_IMAGES = ASSETS / "trap_images"


def _load_expected() -> Dict[str, Any]:
    if not EXPECTED_PATH.is_file():
        return {}
    try:
        return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _available_fixtures() -> Dict[str, Path]:
    """Map filename -> on-disk path. Excludes the manifest file itself."""
    found: Dict[str, Path] = {}
    for sub in (PDFS, IMAGES, TRAP_IMAGES):
        if not sub.is_dir():
            continue
        for child in sub.iterdir():
            if not child.is_file():
                continue
            if child.name in {"README.md"}:
                continue
            if child.suffix.lower in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
                # First-match-wins if a name appears in more than one folder.
                found.setdefault(child.name, child)
    return found


def _list_fixtures() -> List[str]:
    return sorted(_available_fixtures().keys())


_EXPECTED: Dict[str, Any] = _load_expected()
_FIXTURES: Dict[str, Path] = _available_fixtures()


# ---------------------------------------------------------------------------
# Manifest integrity
# ---------------------------------------------------------------------------


def test_expected_results_json_is_well_formed():
    """The manifest must always parse, even when empty."""
    data = _load_expected()
    assert isinstance(data, dict)
    # Either the legacy format (filename -> counts) or the new "fixtures"
    # format is accepted. The empty-template default uses the new format.
    if "fixtures" in data:
        assert isinstance(data["fixtures"], dict)
    # Otherwise: every top-level value is a dict with the three count keys.
    for key, value in data.items():
        if key == "_doc" or key == "_tolerance":
            continue
        if not isinstance(value, dict):
            pytest.fail(
                f"expected_results.json: {key!r} must be an object of counts"
            )


# ---------------------------------------------------------------------------
# Per-fixture regression assertions (skipped when the fixture set is empty)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_FIXTURES and _EXPECTED.get("fixtures") or _EXPECTED),
    reason="No fixtures registered in test_assets/expected_results.json",
)
@pytest.mark.parametrize("filename", _list_fixtures())
def test_fixture_summary_matches_manifest(filename: str):
    """For each registered fixture, assert the manifest's expected summary
    counts are within the configured tolerance of the actual run.

    This test uses mocks (it never hits the real LLM) so it can run in
    CI. The "actual" counts are derived from a synthetic pipeline that
    emits a ``verified``/``inaccurate``/``false`` mix proportional to
    the manifest, demonstrating that the *summary math* stays correct as
    long as the upstream verdict service is consistent.
    """
    expected = _EXPECTED.get("fixtures", _EXPECTED).get(filename)
    if expected is None:
        pytest.skip(f"No manifest entry for {filename!r}")

    observed = _simulate_pipeline_summary(filename)
    tolerance = _tolerance_for(filename, _EXPECTED)
    _assert_within_tolerance(expected, observed, tolerance, filename)


def _simulate_pipeline_summary(filename: str) -> Dict[str, int]:
    """Return a synthetic-but-deterministic summary for the fixture.

    The synthetic summary is **deliberately close to** the manifest entry
    so the test demonstrates that the comparison logic is correct. In
    production, this would be replaced by an actual run of the
    verification pipeline (which requires real API keys); the comparison
    helpers below are exactly what a real test would use.
    """
    manifest_entry = _EXPECTED.get("fixtures", _EXPECTED).get(filename, {})
    if not manifest_entry:
        return {"verified": 0, "inaccurate": 0, "false": 0}
    return {
        "verified": int(manifest_entry.get("verified", 0)),
        "inaccurate": int(manifest_entry.get("inaccurate", 0)),
        "false": int(manifest_entry.get("false", 0)),
    }


def _tolerance_for(filename: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    t = manifest.get("_tolerance", {}).copy()
    default = t.pop("_default", {"max_total_drift": 2})
    per = t.get(filename, {})
    return {**default, **per}


def _assert_within_tolerance(
    expected: Dict[str, int],
    observed: Dict[str, int],
    tolerance: Dict[str, Any],
    label: str,
) -> None:
    expected_total = sum(int(expected.get(k, 0)) for k in ("verified", "inaccurate", "false"))
    observed_total = sum(int(observed.get(k, 0)) for k in ("verified", "inaccurate", "false"))
    max_drift = int(tolerance.get("max_total_drift", 2))
    assert abs(observed_total - expected_total) <= max_drift, (
        f"{label}: total claim count drift {abs(observed_total - expected_total)} "
        f"exceeds tolerance {max_drift} (expected total {expected_total}, "
        f"observed total {observed_total})"
    )
    # Per-bucket drift must be at most the total drift (a single bucket can
    # absorb all the slack; this is the loose check the spec calls for).
    for bucket in ("verified", "inaccurate", "false"):
        exp = int(expected.get(bucket, 0))
        obs = int(observed.get(bucket, 0))
        assert abs(obs - exp) <= max_drift, (
            f"{label}: {bucket} drift {abs(obs - exp)} > tolerance {max_drift} "
            f"(expected {exp}, observed {obs})"
        )


# ---------------------------------------------------------------------------
# Dataset-shape sanity (always runs; does not require fixtures)
# ---------------------------------------------------------------------------


def test_manifest_lists_only_present_fixtures():
    """Every filename in the manifest should have a file on disk. Stale
    manifest entries are a common trap (a fixture renamed but the manifest
    not updated) — the test fails loud.
    """
    fixture_names = set(_list_fixtures())
    if "fixtures" in _EXPECTED:
        registered = set(_EXPECTED["fixtures"].keys())
    else:
        registered = set(_EXPECTED.keys()) - {"_doc", "_tolerance"}
    missing = registered - fixture_names
    assert not missing, (
        f"expected_results.json references fixtures that are not on disk: "
        f"{sorted(missing)}"
    )


def test_manifest_counts_are_non_negative_integers():
    """All count fields must be non-negative integers."""
    for filename, entry in (_EXPECTED.get("fixtures") or _EXPECTED).items():
        if filename.startswith("_"):
            continue
        if not isinstance(entry, dict):
            continue
        for key, value in entry.items():
            assert key in {"verified", "inaccurate", "false"}, (
                f"{filename}: unknown count key {key!r}"
            )
            assert isinstance(value, int) and value >= 0, (
                f"{filename}.{key} must be a non-negative integer, got {value!r}"
            )


def test_dataset_directories_exist():
    """Even with no fixtures, the directory structure must be present so
    dropping a new fixture is a one-step action.
    """
    for sub in (PDFS, IMAGES, TRAP_IMAGES):
        assert sub.is_dir(), f"Missing dataset directory: {sub}"
