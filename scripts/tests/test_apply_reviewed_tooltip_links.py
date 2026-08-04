from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "apply-reviewed-tooltip-links.py"
SPEC = importlib.util.spec_from_file_location("apply_reviewed_tooltip_links", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
APPLY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APPLY
SPEC.loader.exec_module(APPLY)


def test_add_tag_does_not_replace_text_inside_existing_tag() -> None:
    text = (
        '<LSTag Type="Status" Tooltip="INVISIBLE">Невидимость</LSTag> и '
        "Невидимость"
    )

    result = APPLY.add_tag(
        text,
        label="Невидимость",
        type_name="Spell",
        tooltip="Target_Invisibility",
    )

    assert result.count('Tooltip="INVISIBLE"') == 1
    assert result.count('Tooltip="Target_Invisibility"') == 1


def test_apply_manifest_uses_longer_label_before_shorter_one() -> None:
    entries = {"uid": "Высшая невидимость и невидимость."}
    manifest = {
        "additions": [
            {
                "contentuid": "uid",
                "label": "невидимость",
                "type": "Status",
                "tooltip": "INVISIBLE",
            },
            {
                "contentuid": "uid",
                "label": "Высшая невидимость",
                "type": "Spell",
                "tooltip": "Target_Invisibility_Greater",
            },
        ]
    }

    result = APPLY.apply_manifest(entries, manifest)["uid"]

    assert '<LSTag Type="Spell" Tooltip="Target_Invisibility_Greater">Высшая невидимость</LSTag>' in result
    assert '<LSTag Type="Status" Tooltip="INVISIBLE">невидимость</LSTag>' in result


def test_apply_manifest_checks_expected_source_text() -> None:
    with pytest.raises(ValueError, match="Unexpected source text"):
        APPLY.apply_manifest(
            {"uid": "current"},
            {
                "textReplacements": [
                    {
                        "contentuid": "uid",
                        "expectedText": "stale",
                        "replacementText": "new",
                    }
                ]
            },
        )
