import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "resolve-release-tag.py"
SPEC = importlib.util.spec_from_file_location("resolve_release_tag", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def resolve(last_tag: str, parent: str, previous_parent: str) -> tuple[int, int, int]:
    parsed_tag = MODULE.parse_tag(last_tag)
    parsed_baseline = MODULE.parse_tag("v0.4.0")
    assert parsed_tag is not None
    assert parsed_baseline is not None
    result, _ = MODULE.resolve_policy_target(
        last_stable_version=parsed_tag[:3],
        baseline_version=parsed_baseline[:3],
        parent_version=MODULE.parse_parent_version(parent),
        previous_parent_version=MODULE.parse_parent_version(previous_parent),
    )
    return result


def test_moves_existing_series_to_baseline():
    assert resolve("v0.3.161", "4.11.14.0", "4.11.14.0") == (0, 4, 0)


def test_translation_update_increments_patch():
    assert resolve("v0.4.0", "4.11.14.0", "4.11.14.0") == (0, 4, 1)


def test_parent_minor_update_increments_minor_and_resets_patch():
    assert resolve("v0.4.7", "4.12.0.0", "4.11.14.0") == (0, 5, 0)


def test_parent_major_update_increments_major_and_resets_rest():
    assert resolve("v0.8.9", "5.0.0.0", "4.11.14.0") == (1, 0, 0)


def test_parent_version_regression_is_blocked():
    with pytest.raises(ValueError, match="moved backwards"):
        resolve("v0.4.0", "4.10.0.0", "4.11.14.0")
