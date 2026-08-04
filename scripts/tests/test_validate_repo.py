import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts/validate-repo.py"
SPEC = importlib.util.spec_from_file_location("validate_repo", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_precommit_validation_passes_for_repository():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--mode", "pre-commit"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "mode=pre-commit" in result.stdout


def test_release_validation_requires_tag():
    try:
        MODULE.validate_release("", 0)
    except MODULE.ValidationError as exc:
        assert "--version-tag is required" in str(exc)
    else:
        raise AssertionError("validate_release must reject an empty tag")


def test_forbidden_tracked_paths():
    assert MODULE.is_forbidden_tracked_path("build/mod.pak")
    assert MODULE.is_forbidden_tracked_path("config/.env.production")
    assert MODULE.is_forbidden_tracked_path("Mods/example.pak")
    assert not MODULE.is_forbidden_tracked_path(".env.example")
    assert not MODULE.is_forbidden_tracked_path("scripts/build.ps1")
