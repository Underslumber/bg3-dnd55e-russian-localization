#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


BLOCKED_GLOSSARY_TERMS = {
    "Action",
    "Class",
    "Creature",
    "Damage",
    "Feature",
    "Features",
    "Force",
    "History",
    "Level",
    "Magic",
    "Master",
    "Spell",
}
PLACEHOLDER_PATTERN = re.compile(
    r"%\d+\$[sd]|%[sd]|\[\d+\]|&lt;br&gt;|<LSTag[^>]*>|</LSTag>|\{[^}]+\}",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect glossary-driven translation review items for LLM."
    )
    parser.add_argument(
        "-EnglishPath",
        "--english-path",
        default=".cache/upstream/english.xml",
        dest="english_path",
    )
    parser.add_argument(
        "-RussianPath",
        "--russian-path",
        default="Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
        dest="russian_path",
    )
    parser.add_argument(
        "-GlossaryPath",
        "--glossary-path",
        default="glossary/glossary.official.json",
        dest="glossary_path",
    )
    parser.add_argument(
        "-OutputPath",
        "--output-path",
        default="build/glossary-review-input.json",
        dest="output_path",
    )
    parser.add_argument(
        "-TrustedRegistryPath",
        "--trusted-registry-path",
        default="glossary/trusted-contentuid-versions.json",
        dest="trusted_registry_path",
    )
    return parser.parse_args()


def get_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def read_json(path: Path) -> object:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"JSON file was not found: '{resolved_path}'.")
    return json.loads(resolved_path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_optional_trusted_registry(path: Path) -> dict[str, str]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        return {}

    payload = read_json(resolved_path)
    if not isinstance(payload, dict):
        raise ValueError("Trusted registry JSON root must be an object.")

    entries = payload.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("Trusted registry JSON must contain object field 'entries'.")

    trusted: dict[str, str] = {}
    for content_uid, version in entries.items():
        if not isinstance(content_uid, str) or not isinstance(version, str):
            raise ValueError("Trusted registry entries must be string-to-string pairs.")
        trusted[content_uid] = version
    return trusted


def read_localization_entries(path: Path) -> dict[str, dict[str, str]]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Localization XML was not found: '{resolved_path}'.")

    root = ET.fromstring(resolved_path.read_text(encoding="utf-8-sig"))
    if root.tag != "contentList":
        raise ValueError(f"Localization XML does not contain '/contentList': '{resolved_path}'.")

    entries: dict[str, dict[str, str]] = {}
    for node in root.findall("./content"):
        content_uid = str(node.get("contentuid", "")).strip()
        if not content_uid:
            raise ValueError(f"Localization XML contains empty 'contentuid': '{resolved_path}'.")
        if content_uid in entries:
            raise ValueError(f"Localization XML contains duplicate contentuid '{content_uid}'.")
        entries[content_uid] = {
            "contentuid": content_uid,
            "version": str(node.get("version", "") or ""),
            "text": str(node.text or ""),
        }
    return entries


def load_glossary(path: Path) -> dict[str, str]:
    glossary = read_json(path)
    if not isinstance(glossary, dict):
        raise ValueError("Glossary JSON root must be an object.")

    normalized: dict[str, str] = {}
    for english_term, russian_term in glossary.items():
        if not isinstance(english_term, str) or not isinstance(russian_term, str):
            raise ValueError("Glossary JSON must contain only string keys and values.")
        normalized[english_term] = russian_term
    return normalized


def build_glossary_patterns(glossary: dict[str, str]) -> list[tuple[str, str, re.Pattern[str]]]:
    patterns: list[tuple[str, str, re.Pattern[str]]] = []
    for english_term, russian_term in sorted(glossary.items(), key=lambda item: (-len(item[0]), item[0].casefold())):
        source = english_term.strip()
        target = russian_term.strip()
        if len(source) < 4 or source in BLOCKED_GLOSSARY_TERMS or target == "":
            continue
        escaped = re.escape(source)
        if re.fullmatch(r"[A-Za-z0-9 ]+", source):
            pattern = re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
        else:
            pattern = re.compile(escaped, re.IGNORECASE)
        patterns.append((source, target, pattern))
    return patterns


def get_placeholder_tokens(text: str) -> list[str]:
    return PLACEHOLDER_PATTERN.findall(text)


def collect_required_terms(
    *,
    english_text: str,
    russian_text: str,
    glossary_patterns: list[tuple[str, str, re.Pattern[str]]],
) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    occupied_spans: list[tuple[int, int]] = []
    russian_casefold = russian_text.casefold()

    long_prose = len(english_text) > 160 or "\n" in english_text or "<br>" in english_text or ". " in english_text

    for english_term, russian_term, pattern in glossary_patterns:
        if long_prose and " " not in english_term:
            continue
        match = pattern.search(english_text)
        if match is None:
            continue
        if russian_term.casefold() in russian_casefold:
            continue

        span = match.span()
        if any(span[0] < end and span[1] > start for start, end in occupied_spans):
            continue

        occupied_spans.append(span)
        pairs.append(
            {
                "english": english_term,
                "russian": russian_term,
            }
        )

    return pairs


def build_review_items(
    english_entries: dict[str, dict[str, str]],
    russian_entries: dict[str, dict[str, str]],
    glossary_patterns: list[tuple[str, str, re.Pattern[str]]],
    trusted_registry: dict[str, str],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    items: list[dict[str, object]] = []
    stats = {
        "untrusted": 0,
        "version_mismatch": 0,
        "trusted_skipped": 0,
        "missing_in_registry": 0,
    }

    for content_uid in sorted(english_entries):
        english_entry = english_entries[content_uid]
        russian_entry = russian_entries.get(content_uid)
        if russian_entry is None:
            continue

        english_text = str(english_entry["text"] or "")
        russian_text = str(russian_entry["text"] or "")
        required_terms = collect_required_terms(
            english_text=english_text,
            russian_text=russian_text,
            glossary_patterns=glossary_patterns,
        )
        if not required_terms:
            continue

        trusted_version = trusted_registry.get(content_uid)
        current_version = str(russian_entry["version"] or "")
        if trusted_version == current_version and trusted_version != "":
            stats["trusted_skipped"] += 1
            continue

        item: dict[str, object] = {
            "contentuid": content_uid,
            "version": current_version,
            "english_text": english_text,
            "current_russian_text": russian_text,
            "required_glossary_terms": required_terms,
            "english_placeholders": get_placeholder_tokens(english_text),
            "current_russian_placeholders": get_placeholder_tokens(russian_text),
        }
        if trusted_version:
            stats["untrusted"] += 1
            item["trusted_version"] = trusted_version
        else:
            stats["missing_in_registry"] += 1
        if english_entry["version"] != russian_entry["version"]:
            item["notes"] = ["version_mismatch"]
            stats["version_mismatch"] += 1
        items.append(item)

    return items, stats


def main() -> int:
    args = parse_args()

    try:
        english_entries = read_localization_entries(Path(args.english_path))
        russian_entries = read_localization_entries(Path(args.russian_path))
        glossary = load_glossary(Path(args.glossary_path))
        trusted_registry = read_optional_trusted_registry(Path(args.trusted_registry_path))
        glossary_patterns = build_glossary_patterns(glossary)
        items, stats = build_review_items(
            english_entries,
            russian_entries,
            glossary_patterns,
            trusted_registry,
        )

        output_path = Path(args.output_path).resolve()
        write_json(
            output_path,
            {
                "generatedAt": get_now_iso(),
                "englishPath": str(Path(args.english_path).resolve()),
                "russianPath": str(Path(args.russian_path).resolve()),
                "glossaryPath": str(Path(args.glossary_path).resolve()),
                "trustedRegistryPath": str(Path(args.trusted_registry_path).resolve()),
                "itemCount": len(items),
                "summary": stats,
                "items": items,
            },
        )
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[audit-translation-quality.py] "
        f"Collected {len(items)} review items into '{output_path}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
