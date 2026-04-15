#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List contentuid/version pairs that are new or changed against the trusted registry."
    )
    parser.add_argument(
        "-RussianPath",
        "--russian-path",
        default="Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
        dest="russian_path",
    )
    parser.add_argument(
        "-RegistryPath",
        "--registry-path",
        default="glossary/trusted-contentuid-versions.json",
        dest="registry_path",
    )
    parser.add_argument(
        "-OutputPath",
        "--output-path",
        default="build/untrusted-contentuid-versions.json",
        dest="output_path",
    )
    return parser.parse_args()


def get_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def read_localization_entries(path: Path) -> dict[str, str]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Localization XML was not found: '{resolved_path}'.")

    root = ET.fromstring(resolved_path.read_text(encoding="utf-8-sig"))
    if root.tag != "contentList":
        raise ValueError(f"Localization XML does not contain '/contentList': '{resolved_path}'.")

    entries: dict[str, str] = {}
    for node in root.findall("./content"):
        content_uid = str(node.get("contentuid", "")).strip()
        version = str(node.get("version", "")).strip()
        if not content_uid or not version:
            continue
        if content_uid in entries:
            raise ValueError(f"Localization XML contains duplicate contentuid '{content_uid}'.")
        entries[content_uid] = version
    return entries


def read_registry_entries(path: Path) -> dict[str, str]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Trusted registry JSON was not found: '{resolved_path}'.")

    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Trusted registry JSON root must be an object.")

    entries = payload.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("Trusted registry JSON must contain object field 'entries'.")

    normalized: dict[str, str] = {}
    for content_uid, version in entries.items():
        if not isinstance(content_uid, str) or not isinstance(version, str):
            raise ValueError("Trusted registry entries must be string-to-string pairs.")
        normalized[content_uid] = version
    return normalized


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    try:
        russian_path = Path(args.russian_path).resolve()
        registry_path = Path(args.registry_path).resolve()
        output_path = Path(args.output_path).resolve()

        current_entries = read_localization_entries(russian_path)
        trusted_entries = read_registry_entries(registry_path)

        new_or_changed = []
        for content_uid, version in sorted(current_entries.items()):
            trusted_version = trusted_entries.get(content_uid)
            if trusted_version == version:
                continue
            new_or_changed.append(
                {
                    "contentuid": content_uid,
                    "version": version,
                    "trustedVersion": trusted_version,
                }
            )

        write_json(
            output_path,
            {
                "generatedAt": get_now_iso(),
                "sourceRussianPath": str(russian_path),
                "registryPath": str(registry_path),
                "count": len(new_or_changed),
                "items": new_or_changed,
            },
        )
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[filter-trusted-contentuid-registry.py] "
        f"Found {len(new_or_changed)} new or changed entries in '{output_path}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
