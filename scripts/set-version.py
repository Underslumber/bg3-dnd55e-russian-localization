#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


TAG_PATTERN = re.compile(
    r"^(?P<base>\d+\.\d+\.\d+)(?:-(?P<suffix>[0-9A-Za-z][0-9A-Za-z.-]*))?$"
)
MODULE_INFO_VERSION_PATTERN = re.compile(
    r'(?s)(<node id="ModuleInfo">\s*(?:(?!<children>).)*?<attribute id="Version64" type="int64" value=")\d+("/>)'
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update ModuleInfo/Version64 in meta.lsx from a release tag."
    )
    parser.add_argument(
        "-VersionTag",
        "--version-tag",
        required=True,
        dest="version_tag",
        help="Release tag in the format vX.Y.Z or vX.Y.Z-suffix.",
    )
    parser.add_argument(
        "-MetaPath",
        "--meta-path",
        default="Mods/DnD 5.5e AIO Russian/meta.lsx",
        dest="meta_path",
        help="Path to meta.lsx.",
    )
    parser.add_argument(
        "-RepositoryPath",
        "--repository-path",
        default=".",
        dest="repository_path",
        help="Repository root used to inspect existing git tags.",
    )
    return parser.parse_args()


def get_release_version_parts(tag: str, repo_path: Path) -> tuple[str, str | None, int]:
    normalized = tag[1:] if tag.startswith("v") else tag
    match = TAG_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(
            f"Version tag '{tag}' is invalid. Expected format: vX.Y.Z or vX.Y.Z-suffix"
        )

    base_version = match.group("base")
    suffix = match.group("suffix")
    numbers = [int(part) for part in base_version.split(".")] + [0]

    if suffix:
        numbers[3] = get_suffixed_build_number(tag=tag, base_version=base_version, repo_path=repo_path)

    version64 = (
        (numbers[0] << 55)
        | (numbers[1] << 47)
        | (numbers[2] << 31)
        | numbers[3]
    )
    return base_version, suffix, version64


def get_suffixed_build_number(tag: str, base_version: str, repo_path: Path) -> int:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path.resolve()), "tag", "--list", f"v{base_version}-*"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return 1

    if result.returncode != 0:
        return 1

    matching_tags = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and line.strip() != tag
    ]
    return len(matching_tags) + 1


def ensure_module_info_version_exists(meta_xml: ET.ElementTree, meta_path: Path) -> None:
    module_info_version_node = meta_xml.find(
        './region/node/children/node[@id="ModuleInfo"]/attribute[@id="Version64"][@type="int64"]'
    )
    if module_info_version_node is None:
        raise ValueError(f"ModuleInfo/Version64 attribute was not found in '{meta_path}'.")


def update_meta(meta_path: Path, resolved_version64: int) -> None:
    if not meta_path.exists():
        raise FileNotFoundError(f"meta.lsx was not found: '{meta_path}'.")

    meta_content = meta_path.read_text(encoding="utf-8")
    meta_xml = ET.ElementTree(ET.fromstring(meta_content))
    ensure_module_info_version_exists(meta_xml, meta_path)

    if MODULE_INFO_VERSION_PATTERN.search(meta_content) is None:
        raise ValueError(f"ModuleInfo/Version64 attribute was not found in '{meta_path}'.")

    updated_meta, replacements = MODULE_INFO_VERSION_PATTERN.subn(
        rf"\g<1>{resolved_version64}\g<2>",
        meta_content,
        count=1,
    )
    if replacements != 1:
        raise ValueError(f"ModuleInfo/Version64 attribute was not found in '{meta_path}'.")

    meta_path.write_text(updated_meta, encoding="utf-8", newline="")


def main() -> int:
    args = parse_args()
    meta_path = Path(args.meta_path).resolve()
    repository_path = Path(args.repository_path).resolve()

    try:
        base_version, _, version64 = get_release_version_parts(
            tag=args.version_tag,
            repo_path=repository_path,
        )
        update_meta(meta_path=meta_path, resolved_version64=version64)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        f"[set-version.py] Updated '{meta_path}' to Version64={version64} "
        f"(from tag '{args.version_tag}', base '{base_version}')."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
