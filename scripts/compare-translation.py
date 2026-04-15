#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare upstream English and Russian localization.")
    parser.add_argument("-EnglishPath", "--english-path", default=".cache/upstream/english.xml", dest="english_path")
    parser.add_argument(
        "-RussianPath",
        "--russian-path",
        default="Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
        dest="russian_path",
    )
    parser.add_argument("-OutputDir", "--output-dir", default="build/translation-diff", dest="output_dir")
    parser.add_argument(
        "--from-scratch",
        action="store_true",
        dest="from_scratch",
        default=False,
        help=(
            "Treat all English entries as missing: back up current russian.xml to .cache/backup/, "
            "replace it with an empty <contentList>, and put all entries in candidates.adds "
            "with oldRussianText populated from the backup."
        ),
    )
    return parser.parse_args()


def get_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def get_localization_entries(path: Path) -> dict[str, dict[str, str]]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Localization XML was not found: '{resolved_path}'.")

    root = ET.fromstring(resolved_path.read_text(encoding="utf-8-sig"))
    if root.tag != "contentList":
        raise ValueError(
            f"Localization XML does not contain '/contentList/content' nodes: '{resolved_path}'."
        )

    entries: dict[str, dict[str, str]] = {}
    for node in root.findall("./content"):
        content_uid = node.get("contentuid", "")
        if not content_uid.strip():
            raise ValueError(
                f"Localization XML contains a content node without 'contentuid': '{resolved_path}'."
            )
        if content_uid in entries:
            raise ValueError(
                f"Localization XML contains duplicate contentuid '{content_uid}': '{resolved_path}'."
            )

        version = node.get("version", "")
        if not version.strip():
            raise ValueError(
                f"Localization XML contains contentuid '{content_uid}' with empty 'version': '{resolved_path}'."
            )

        entries[content_uid] = {
            "contentuid": content_uid,
            "version": version,
            "text": node.text or "",
        }

    return entries


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def backup_and_clear_russian_xml(russian_path: Path) -> Path:
    backup_dir = Path(".cache/backup").resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"russian.{timestamp}.xml"
    backup_path.write_bytes(russian_path.read_bytes())

    empty_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        "<contentList>\n"
        "</contentList>\n"
    )
    russian_path.write_bytes(b"\xef\xbb\xbf" + empty_xml.encode("utf-8"))
    return backup_path


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        english_entries = get_localization_entries(Path(args.english_path))

        # In from-scratch mode: load current RU for reference, then clear it.
        backup_path: Path | None = None
        if args.from_scratch:
            russian_path_resolved = Path(args.russian_path).resolve()
            old_russian_entries = get_localization_entries(russian_path_resolved)
            backup_path = backup_and_clear_russian_xml(russian_path_resolved)
            print(f"[compare-translation.py] Backed up russian.xml to '{backup_path}'.")
            # After clearing, treat RU as empty for comparison.
            russian_entries: dict[str, dict[str, str]] = {}
        else:
            old_russian_entries = {}
            russian_entries = get_localization_entries(Path(args.russian_path))

        missing_in_russian: list[dict[str, str]] = []
        version_mismatch: list[dict[str, str]] = []
        stale_only_in_russian: list[dict[str, str]] = []

        for content_uid in sorted(english_entries):
            english_entry = english_entries[content_uid]
            russian_entry = russian_entries.get(content_uid)
            if russian_entry is None:
                item: dict[str, str] = {
                    "contentuid": content_uid,
                    "englishVersion": english_entry["version"],
                    "englishText": english_entry["text"],
                }
                if args.from_scratch:
                    item["oldRussianText"] = old_russian_entries.get(content_uid, {}).get("text", "")
                missing_in_russian.append(item)
                continue

            if english_entry["version"] != russian_entry["version"]:
                version_mismatch.append(
                    {
                        "contentuid": content_uid,
                        "englishVersion": english_entry["version"],
                        "russianVersion": russian_entry["version"],
                        "englishText": english_entry["text"],
                        "russianText": russian_entry["text"],
                    }
                )

        for content_uid in sorted(russian_entries):
            if content_uid not in english_entries:
                russian_entry = russian_entries[content_uid]
                stale_only_in_russian.append(
                    {
                        "contentuid": content_uid,
                        "russianVersion": russian_entry["version"],
                        "russianText": russian_entry["text"],
                    }
                )

        summary = {
            "generatedAt": get_now_iso(),
            "fromScratch": args.from_scratch,
            "backupPath": str(backup_path) if backup_path is not None else None,
            "englishPath": str(Path(args.english_path).resolve()),
            "russianPath": str(Path(args.russian_path).resolve()),
            "englishCount": len(english_entries),
            "russianCount": len(russian_entries),
            "missingInRussianCount": len(missing_in_russian),
            "versionMismatchCount": len(version_mismatch),
            "staleOnlyInRussianCount": len(stale_only_in_russian),
            "missingInRussian": missing_in_russian,
            "versionMismatch": version_mismatch,
            "staleOnlyInRussian": stale_only_in_russian,
        }

        add_entries: list[dict[str, str]] = []
        for item in missing_in_russian:
            entry: dict[str, str] = {
                "contentuid": item["contentuid"],
                "version": item["englishVersion"],
                "text": "",
                "englishText": item["englishText"],
            }
            if args.from_scratch and item.get("oldRussianText"):
                entry["oldRussianText"] = item["oldRussianText"]
            add_entries.append(entry)

        candidates = {
            "generatedAt": get_now_iso(),
            "fromScratch": args.from_scratch,
            "source": {
                "englishPath": str(Path(args.english_path).resolve()),
                "russianPath": str(Path(args.russian_path).resolve()),
                **({"backupPath": str(backup_path)} if backup_path is not None else {}),
            },
            "updates": [
                {
                    "contentuid": item["contentuid"],
                    "version": item["englishVersion"],
                    "text": item["russianText"],
                    "englishText": item["englishText"],
                    "russianVersion": item["russianVersion"],
                }
                for item in version_mismatch
            ],
            "adds": add_entries,
        }

        summary_json_path = output_dir / "summary.json"
        summary_md_path = output_dir / "summary.md"
        candidates_json_path = output_dir / "candidates.json"
        write_json(summary_json_path, summary)
        write_json(candidates_json_path, candidates)

        is_up_to_date = not missing_in_russian and not version_mismatch and not stale_only_in_russian
        md_lines = [
            "# Translation diff summary",
            "",
            f"- Generated: {summary['generatedAt']}",
        ]
        if args.from_scratch:
            md_lines.append("- Mode: **from-scratch**")
            if backup_path is not None:
                md_lines.append(f"- Backup: `{backup_path}`")
        md_lines.extend(
            [
                f"- English entries: {summary['englishCount']}",
                f"- Russian entries: {summary['russianCount']}",
                f"- Missing in Russian: {summary['missingInRussianCount']}",
                f"- Version mismatches: {summary['versionMismatchCount']}",
                f"- Stale only in Russian: {summary['staleOnlyInRussianCount']}",
                "",
            ]
        )

        if is_up_to_date:
            md_lines.append("Перевод уже актуален, дополнительные действия не требуются.")
        else:
            md_lines.extend(
                [
                    "",
                    "## Agent workflow",
                    "1. Refresh upstream cache: ``scripts/get-upstream-english.py``",
                    "2. Refresh diff reports: ``scripts/compare-translation.py``",
                    "3. Fill translated texts in ``build/translation-diff/candidates.json``",
                    "4. Apply only prepared edits: ``scripts/apply-translation-edits.py -EditsPath build/translation-diff/candidates.json``",
                ]
            )

        md_lines.extend(["", "## Missing in Russian"])
        if missing_in_russian:
            md_lines.extend(
                [
                    f"- ``{item['contentuid']}`` v{item['englishVersion']}: {item['englishText']}"
                    for item in missing_in_russian[:50]
                ]
            )
        else:
            md_lines.append("- none")

        md_lines.extend(["", "## Version mismatches"])
        if version_mismatch:
            md_lines.extend(
                [
                    f"- ``{item['contentuid']}`` en=v{item['englishVersion']}, ru=v{item['russianVersion']}"
                    for item in version_mismatch[:50]
                ]
            )
        else:
            md_lines.append("- none")

        md_lines.extend(["", "## Stale only in Russian"])
        if stale_only_in_russian:
            md_lines.extend(
                [
                    f"- ``{item['contentuid']}`` v{item['russianVersion']}: {item['russianText']}"
                    for item in stale_only_in_russian[:50]
                ]
            )
        else:
            md_lines.append("- none")

        summary_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"[compare-translation.py] Summary written to '{summary_json_path}' and '{summary_md_path}'.")
    print(f"[compare-translation.py] Editable candidate file written to '{candidates_json_path}'.")
    print(
        "[compare-translation.py] "
        f"Missing={len(missing_in_russian)}; VersionMismatch={len(version_mismatch)}; "
        f"StaleOnlyInRussian={len(stale_only_in_russian)}."
    )
    if args.from_scratch:
        print(f"[compare-translation.py] from-scratch mode: russian.xml cleared, backup at '{backup_path}'.")
    elif is_up_to_date:
        print("[compare-translation.py] Перевод уже актуален, дополнительные действия не требуются.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
