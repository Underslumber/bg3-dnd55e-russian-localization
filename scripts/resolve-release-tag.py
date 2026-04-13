#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


TAG_PATTERN = re.compile(
    r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<suffix>[0-9A-Za-z][0-9A-Za-z.-]*))?$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve the next release tag for the autopilot workflow.")
    parser.add_argument(
        "-RepositoryPath",
        "--repository-path",
        default=".",
        dest="repository_path",
    )
    parser.add_argument(
        "-ReleaseChannel",
        "--release-channel",
        choices=("stable", "prerelease"),
        default="stable",
        dest="release_channel",
    )
    parser.add_argument(
        "-CustomTag",
        "--custom-tag",
        default="",
        dest="custom_tag",
    )
    parser.add_argument(
        "-OutputPath",
        "--output-path",
        default="build/autopilot/resolved-tag.json",
        dest="output_path",
    )
    return parser.parse_args()


def run_git_tag_list(repository_path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repository_path), "tag", "--list"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "Failed to list git tags.")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def parse_tag(tag: str) -> tuple[int, int, int, str | None] | None:
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        match.group("suffix"),
    )


def format_base(version: tuple[int, int, int]) -> str:
    return f"{version[0]}.{version[1]}.{version[2]}"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def next_patch(version: tuple[int, int, int]) -> tuple[int, int, int]:
    return version[0], version[1], version[2] + 1


def main() -> int:
    args = parse_args()
    repository_path = Path(args.repository_path).resolve()
    output_path = Path(args.output_path).resolve()

    try:
        tags = run_git_tag_list(repository_path)
        parsed_tags = [(tag, parse_tag(tag)) for tag in tags]
        valid_tags = [(tag, parsed) for tag, parsed in parsed_tags if parsed is not None]
        stable_versions = [
            (tag, (parsed[0], parsed[1], parsed[2]))
            for tag, parsed in valid_tags
            if parsed is not None and parsed[3] is None
        ]

        if args.custom_tag.strip():
            custom_tag = args.custom_tag.strip()
            parsed_custom = parse_tag(custom_tag)
            if parsed_custom is None:
                raise ValueError(
                    f"Custom tag '{custom_tag}' is invalid. Expected format: vX.Y.Z or vX.Y.Z-suffix."
                )
            if custom_tag in tags:
                raise ValueError(f"Tag '{custom_tag}' already exists.")

            resolved_tag = custom_tag
            base_version = (parsed_custom[0], parsed_custom[1], parsed_custom[2])
            source = "custom"
        else:
            last_stable_version = max((version for _, version in stable_versions), default=(0, 0, 0))
            target_base = next_patch(last_stable_version)

            if args.release_channel == "stable":
                resolved_tag = f"v{format_base(target_base)}"
            else:
                target_base_label = format_base(target_base)
                existing_suffixed = [
                    tag
                    for tag, parsed in valid_tags
                    if parsed is not None
                    and (parsed[0], parsed[1], parsed[2]) == target_base
                    and parsed[3] is not None
                ]
                suffix_index = len(existing_suffixed) + 1
                resolved_tag = f"v{target_base_label}-rc.{suffix_index}"

            if resolved_tag in tags:
                raise ValueError(f"Resolved tag '{resolved_tag}' already exists.")

            base_version = target_base
            source = "auto"

        report = {
            "releaseChannel": args.release_channel,
            "resolvedTag": resolved_tag,
            "baseVersion": format_base(base_version),
            "source": source,
            "customTagProvided": bool(args.custom_tag.strip()),
            "validTagCount": len(valid_tags),
            "stableTagCount": len(stable_versions),
        }
        write_json(output_path, report)
    except (OSError, RuntimeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[resolve-release-tag.py] "
        f"ResolvedTag={report['resolvedTag']}; Channel={report['releaseChannel']}; Source={report['source']}."
    )
    print(f"[resolve-release-tag.py] Report written to '{output_path}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
