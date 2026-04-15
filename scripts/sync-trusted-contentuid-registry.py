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
        description="Sync trusted contentuid/version registry from russian.xml."
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

        if not content_uid:
            raise ValueError(f"Localization XML contains empty 'contentuid': '{resolved_path}'.")
        if not version:
            raise ValueError(
                f"Localization XML contains contentuid '{content_uid}' with empty 'version': '{resolved_path}'."
            )
        if content_uid in entries:
            raise ValueError(f"Localization XML contains duplicate contentuid '{content_uid}'.")

        entries[content_uid] = version

    return entries


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    try:
        russian_path = Path(args.russian_path).resolve()
        registry_path = Path(args.registry_path).resolve()
        entries = read_localization_entries(russian_path)
        payload = {
            "generatedAt": get_now_iso(),
            "sourceRussianPath": str(russian_path),
            "entryCount": len(entries),
            "entries": dict(sorted(entries.items())),
        }
        write_json(registry_path, payload)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[sync-trusted-contentuid-registry.py] "
        f"Registry written to '{registry_path}' with {len(entries)} trusted entries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
