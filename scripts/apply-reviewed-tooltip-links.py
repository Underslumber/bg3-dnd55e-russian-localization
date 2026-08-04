#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path


CONTENT_PATTERN = re.compile(
    r'(?P<open><content\b[^>]*\bcontentuid="(?P<uid>[^"]+)"[^>]*>)'
    r'(?P<body>.*?)'
    r'(?P<close></content>)',
    re.DOTALL,
)
LSTAG_PATTERN = re.compile(r"<LSTag\b[^>]*>.*?</LSTag>", re.IGNORECASE | re.DOTALL)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply context-reviewed tooltip links without reformatting russian.xml."
    )
    parser.add_argument("manifest_path")
    parser.add_argument("russian_path")
    return parser.parse_args()


def add_tag(text: str, *, label: str, type_name: str, tooltip: str) -> str:
    parts = LSTAG_PATTERN.split(text)
    tags = LSTAG_PATTERN.findall(text)
    pattern = re.compile(re.escape(label), re.IGNORECASE)

    for index, part in enumerate(parts):
        match = pattern.search(part)
        if match is None:
            continue
        matched_label = match.group(0)
        replacement = (
            f'<LSTag Type="{type_name}" Tooltip="{tooltip}">{matched_label}</LSTag>'
        )
        parts[index] = part[: match.start()] + replacement + part[match.end() :]
        rebuilt: list[str] = []
        for part_index, current_part in enumerate(parts):
            rebuilt.append(current_part)
            if part_index < len(tags):
                rebuilt.append(tags[part_index])
        return "".join(rebuilt)

    raise ValueError(
        f"Cannot add {type_name}:{tooltip}: label {label!r} is absent outside LSTag"
    )


def apply_manifest(
    entries: dict[str, str], manifest: dict[str, object]
) -> dict[str, str]:
    changed = dict(entries)

    for replacement in manifest.get("textReplacements", []):
        uid = replacement["contentuid"]
        expected = replacement["expectedText"]
        if changed.get(uid) != expected:
            raise ValueError(f"Unexpected source text for {uid}")
        changed[uid] = replacement["replacementText"]

    additions_by_uid: dict[str, list[dict[str, str]]] = {}
    for addition in manifest.get("additions", []):
        additions_by_uid.setdefault(addition["contentuid"], []).append(addition)

    for uid, additions in additions_by_uid.items():
        if uid not in changed:
            raise ValueError(f"Unknown contentuid: {uid}")
        current = changed[uid]
        # Longer labels first so a phrase such as "Высшая невидимость" is not
        # consumed by the shorter entity name "Невидимость".
        for addition in sorted(additions, key=lambda item: len(item["label"]), reverse=True):
            try:
                current = add_tag(
                    current,
                    label=addition["label"],
                    type_name=addition["type"],
                    tooltip=addition["tooltip"],
                )
            except ValueError as exc:
                raise ValueError(f"{uid}: {exc}") from exc
        changed[uid] = current

    return changed


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest_path)
    russian_path = Path(args.russian_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = russian_path.read_text(encoding="utf-8")

    entries: dict[str, str] = {}
    for match in CONTENT_PATTERN.finditer(source):
        entries[match.group("uid")] = html.unescape(match.group("body"))
    changed = apply_manifest(entries, manifest)

    changed_uids = {uid for uid in entries if entries[uid] != changed[uid]}

    def replace_content(match: re.Match[str]) -> str:
        uid = match.group("uid")
        if uid not in changed_uids:
            return match.group(0)
        encoded = html.escape(changed[uid], quote=False)
        return match.group("open") + encoded + match.group("close")

    updated = CONTENT_PATTERN.sub(replace_content, source)
    russian_path.write_text(updated, encoding="utf-8", newline="")
    print(
        f"[apply-reviewed-tooltip-links.py] changed_entries={len(changed_uids)}; "
        f"additions={len(manifest.get('additions', []))}; "
        f"text_replacements={len(manifest.get('textReplacements', []))}."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
