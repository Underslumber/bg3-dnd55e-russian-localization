#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALIZATION = ROOT / "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml"
META = ROOT / "Mods/DnD 5.5e AIO Russian/meta.lsx"
MODULE_INFO_XPATH = './region/node/children/node[@id="ModuleInfo"]'
REQUIRED_PATHS = (
    LOCALIZATION,
    META,
    ROOT / "scripts/build.ps1",
    ROOT / ".github/workflows/build.yml",
    ROOT / "glossary/glossary.official.json",
    ROOT / "glossary/glossary.normalized.json",
)
REQUIRED_IGNORES = {
    "build/",
    "build-stage*",
    ".tools/",
    ".cache/",
    ".env.local",
    "*.pak",
}
EXPECTED_PUBLISH_VERSION64 = 281477124194304


class ValidationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate repository and release invariants."
    )
    parser.add_argument(
        "--mode",
        choices=("pre-commit", "pre-release"),
        default="pre-commit",
    )
    parser.add_argument("--version-tag", default="")
    return parser.parse_args()


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValidationError(detail or f"Command failed: {' '.join(command)}")
    return result


def validate_required_paths() -> None:
    missing = [
        str(path.relative_to(ROOT)) for path in REQUIRED_PATHS if not path.exists()
    ]
    if missing:
        raise ValidationError(f"Missing required paths: {', '.join(missing)}")


def validate_gitignore() -> None:
    ignore_path = ROOT / ".gitignore"
    lines = {
        line.strip()
        for line in ignore_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing = sorted(REQUIRED_IGNORES - lines)
    if missing:
        raise ValidationError(
            f".gitignore is missing required rules: {', '.join(missing)}"
        )


def is_forbidden_tracked_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    basename = normalized.rsplit("/", 1)[-1]
    return (
        normalized.endswith(".pak")
        or (basename.startswith(".env") and basename != ".env.example")
        or normalized.startswith(("build/", ".tools/", ".cache/", "build-stage"))
    )


def validate_tracked_files() -> None:
    tracked = run(["git", "ls-files", "-z"]).stdout.split("\0")
    forbidden = [path for path in tracked if path and is_forbidden_tracked_path(path)]
    if forbidden:
        raise ValidationError(
            f"Forbidden tracked files: {', '.join(sorted(forbidden))}"
        )


def validate_localization() -> None:
    root = ET.fromstring(LOCALIZATION.read_text(encoding="utf-8-sig"))
    if root.tag != "contentList":
        raise ValidationError("russian.xml root must be contentList")
    nodes = root.findall("./content")
    if not nodes:
        raise ValidationError("russian.xml has no content entries")
    seen: set[str] = set()
    for node in nodes:
        content_uid = (node.get("contentuid") or "").strip()
        version = (node.get("version") or "").strip()
        if not content_uid or not version:
            raise ValidationError(
                "Every localization entry must have contentuid and version"
            )
        if content_uid in seen:
            raise ValidationError(f"Duplicate localization contentuid: {content_uid}")
        seen.add(content_uid)


def read_meta_versions() -> tuple[int, int]:
    root = ET.fromstring(META.read_text(encoding="utf-8-sig"))
    module_info = root.find(MODULE_INFO_XPATH)
    if module_info is None:
        raise ValidationError("meta.lsx ModuleInfo node was not found")
    version_node = module_info.find('./attribute[@id="Version64"][@type="int64"]')
    publish_node = module_info.find(
        './children/node[@id="PublishVersion"]/attribute[@id="Version64"][@type="int64"]'
    )
    if version_node is None or publish_node is None:
        raise ValidationError(
            "meta.lsx Version64 or PublishVersion/Version64 was not found"
        )
    try:
        return int(version_node.attrib["value"]), int(publish_node.attrib["value"])
    except (KeyError, ValueError) as exc:
        raise ValidationError("meta.lsx version values must be int64") from exc


def validate_publish_version_unchanged(current_publish_version: int) -> None:
    if current_publish_version != EXPECTED_PUBLISH_VERSION64:
        raise ValidationError(
            "PublishVersion/Version64 must remain "
            f"{EXPECTED_PUBLISH_VERSION64}, got {current_publish_version}"
        )


def load_set_version_module():
    path = ROOT / "scripts/set-version.py"
    spec = importlib.util.spec_from_file_location("set_version", path)
    if spec is None or spec.loader is None:
        raise ValidationError("Cannot load scripts/set-version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_release(version_tag: str, actual_version64: int) -> None:
    if not version_tag:
        raise ValidationError("--version-tag is required in pre-release mode")
    status = run(["git", "status", "--porcelain"]).stdout.strip()
    if status:
        raise ValidationError("Pre-release validation requires a clean worktree")
    module = load_set_version_module()
    try:
        _, _, expected_version64 = module.get_release_version_parts(version_tag, ROOT)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if actual_version64 != expected_version64:
        raise ValidationError(
            f"Version mismatch: tag {version_tag} requires Version64={expected_version64}, "
            f"meta.lsx has {actual_version64}"
        )


def validate_diff() -> None:
    run(["git", "diff", "--check"])
    run(["git", "diff", "--cached", "--check"])


def main() -> int:
    args = parse_args()
    try:
        validate_required_paths()
        validate_gitignore()
        validate_tracked_files()
        validate_localization()
        actual_version64, publish_version64 = read_meta_versions()
        validate_publish_version_unchanged(publish_version64)
        validate_diff()
        if args.mode == "pre-release":
            validate_release(args.version_tag, actual_version64)
    except (OSError, ET.ParseError, ValidationError) as exc:
        print(f"[validate-repo.py] ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"[validate-repo.py] OK: mode={args.mode}, "
        f"Version64={actual_version64}, PublishVersion64={publish_version64}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
