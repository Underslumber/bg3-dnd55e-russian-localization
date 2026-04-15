#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


VALID_MODES = ("incremental", "full")


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
        "-Mode",
        "--mode",
        default="incremental",
        choices=VALID_MODES,
        dest="mode",
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
        raise ValueError(f"Localization XML does not contain '/contentList/content' nodes: '{resolved_path}'.")

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


def build_add_entry(english_entry: dict[str, str]) -> dict[str, str]:
    return {
        "contentuid": english_entry["contentuid"],
        "version": english_entry["version"],
        "text": "",
        "englishText": english_entry["text"],
        "changeKind": "translate",
    }


def build_update_entry(
    english_entry: dict[str, str],
    russian_entry: dict[str, str],
) -> dict[str, str]:
    return {
        "contentuid": english_entry["contentuid"],
        "version": english_entry["version"],
        "englishText": english_entry["text"],
        "currentRussianText": russian_entry["text"],
        "russianVersion": russian_entry["version"],
        "changeKind": "review",
    }


def build_delete_entry(russian_entry: dict[str, str]) -> dict[str, str]:
    return {
        "contentuid": russian_entry["contentuid"],
        "version": russian_entry["version"],
        "currentRussianText": russian_entry["text"],
        "changeKind": "delete",
    }


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        english_entries = get_localization_entries(Path(args.english_path))
        source_russian_entries = get_localization_entries(Path(args.russian_path))
        compared_russian_entries = source_russian_entries if args.mode == "incremental" else {}

        missing_in_russian: list[dict[str, str]] = []
        version_mismatch: list[dict[str, str]] = []
        stale_only_in_russian: list[dict[str, str]] = []

        add_entries: list[dict[str, str]] = []
        update_entries: list[dict[str, str]] = []
        delete_entries: list[dict[str, str]] = []

        for content_uid, english_entry in english_entries.items():
            russian_entry = compared_russian_entries.get(content_uid)
            if russian_entry is None:
                missing_in_russian.append(
                    {
                        "contentuid": content_uid,
                        "englishVersion": english_entry["version"],
                        "englishText": english_entry["text"],
                    }
                )
                add_entries.append(build_add_entry(english_entry))
                continue

            if english_entry["version"] != russian_entry["version"]:
                version_mismatch.append(
                    {
                        "contentuid": content_uid,
                        "englishVersion": english_entry["version"],
                        "russianVersion": russian_entry["version"],
                        "englishText": english_entry["text"],
                        "currentRussianText": russian_entry["text"],
                    }
                )
                update_entries.append(build_update_entry(english_entry, russian_entry))

        if args.mode == "incremental":
            for content_uid, russian_entry in source_russian_entries.items():
                if content_uid in english_entries:
                    continue

                stale_only_in_russian.append(
                    {
                        "contentuid": content_uid,
                        "russianVersion": russian_entry["version"],
                        "currentRussianText": russian_entry["text"],
                    }
                )
                delete_entries.append(build_delete_entry(russian_entry))

        summary = {
            "generatedAt": get_now_iso(),
            "mode": args.mode,
            "englishPath": str(Path(args.english_path).resolve()),
            "russianPath": str(Path(args.russian_path).resolve()),
            "englishCount": len(english_entries),
            "sourceRussianCount": len(source_russian_entries),
            "russianCount": len(compared_russian_entries),
            "missingInRussianCount": len(missing_in_russian),
            "versionMismatchCount": len(version_mismatch),
            "staleOnlyInRussianCount": len(stale_only_in_russian),
            "addCount": len(add_entries),
            "updateCount": len(update_entries),
            "deleteCount": len(delete_entries),
            "missingInRussian": missing_in_russian,
            "versionMismatch": version_mismatch,
            "staleOnlyInRussian": stale_only_in_russian,
        }

        candidates = {
            "generatedAt": get_now_iso(),
            "mode": args.mode,
            "source": {
                "englishPath": str(Path(args.english_path).resolve()),
                "russianPath": str(Path(args.russian_path).resolve()),
            },
            "updates": update_entries,
            "adds": add_entries,
            "deletes": delete_entries,
        }

        summary_json_path = output_dir / "summary.json"
        summary_md_path = output_dir / "summary.md"
        candidates_json_path = output_dir / "candidates.json"
        write_json(summary_json_path, summary)
        write_json(candidates_json_path, candidates)

        is_up_to_date = not add_entries and not update_entries and not delete_entries
        md_lines = [
            "# Translation diff summary",
            "",
            f"- Generated: {summary['generatedAt']}",
            f"- Mode: {summary['mode']}",
            f"- English entries: {summary['englishCount']}",
            f"- Source Russian entries: {summary['sourceRussianCount']}",
            f"- Compared Russian entries: {summary['russianCount']}",
            f"- Adds: {summary['addCount']}",
            f"- Reviews: {summary['updateCount']}",
            f"- Deletes: {summary['deleteCount']}",
            "",
        ]

        if is_up_to_date:
            md_lines.append("Перевод уже актуален, дополнительные действия не требуются.")
        else:
            md_lines.extend(
                [
                    "## Skill workflow",
                    "1. Refresh upstream cache into a temporary directory.",
                    "2. Build temporary diff and candidates JSON.",
                    "3. Prepare batched translate/review context with `prepare-translation-context.py`.",
                    "4. Materialize final candidates JSON from agent responses.",
                    "5. Apply edits to a temporary target XML and validate it before replacing the real file.",
                ]
            )

        md_lines.extend(["", "## Adds"])
        if add_entries:
            md_lines.extend(
                [
                    f"- ``{item['contentuid']}`` v{item['version']}: {item['englishText']}"
                    for item in add_entries[:50]
                ]
            )
        else:
            md_lines.append("- none")

        md_lines.extend(["", "## Reviews"])
        if update_entries:
            md_lines.extend(
                [
                    f"- ``{item['contentuid']}`` en=v{item['version']}, ru=v{item['russianVersion']}"
                    for item in update_entries[:50]
                ]
            )
        else:
            md_lines.append("- none")

        md_lines.extend(["", "## Deletes"])
        if delete_entries:
            md_lines.extend(
                [
                    f"- ``{item['contentuid']}`` v{item['version']}: {item['currentRussianText']}"
                    for item in delete_entries[:50]
                ]
            )
        else:
            md_lines.append("- none")

        summary_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"[translation-update:compare] Summary written to '{summary_json_path}' and '{summary_md_path}'.")
    print(f"[translation-update:compare] Editable candidate file written to '{candidates_json_path}'.")
    print(
        "[translation-update:compare] "
        f"Mode={args.mode}; Adds={len(add_entries)}; Reviews={len(update_entries)}; Deletes={len(delete_entries)}."
    )
    if is_up_to_date:
        print("[translation-update:compare] Перевод уже актуален, дополнительные действия не требуются.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
