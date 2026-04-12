#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape


DEFAULT_PARENT_META_URL = (
    "https://raw.githubusercontent.com/Yoonmoonsik/dnd55e/main/"
    "Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/meta.lsx"
)
REQUIRED_FIELDS = ("Folder", "MD5", "Name", "PublishHandle", "UUID", "Version64")
MODULE_SHORT_DESC_PATTERN = re.compile(
    r'(?s)(<node id="ModuleShortDesc">\s*)(.*?)(\s*</node>)'
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync dependency ModuleShortDesc fields from the parent mod meta.lsx."
    )
    parser.add_argument(
        "-ParentMetaUrl",
        "--parent-meta-url",
        default=DEFAULT_PARENT_META_URL,
        dest="parent_meta_url",
        help="URL of the parent mod meta.lsx.",
    )
    parser.add_argument(
        "-TargetMetaPath",
        "--target-meta-path",
        default="Mods/DnD 5.5e AIO Russian/meta.lsx",
        dest="target_meta_path",
        help="Path to the target meta.lsx file.",
    )
    return parser.parse_args()


def decode_xml_bytes(raw: bytes) -> tuple[str, bool]:
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    encoding = "utf-8-sig" if has_bom else "utf-8"
    return raw.decode(encoding), has_bom


def load_text_file(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    return decode_xml_bytes(raw)


def download_parent_meta(url: str) -> str:
    if not url.strip():
        raise ValueError("ParentMetaUrl must not be empty.")

    request = urllib.request.Request(url, headers={"User-Agent": "bg3-dnd55e-sync-parent-meta/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Failed to download parent meta.lsx from '{url}': {exc}"
        ) from exc

    text, _ = decode_xml_bytes(raw)
    return text


def parse_xml(text: str, source: str) -> ET.Element:
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML in '{source}': {exc}") from exc


def get_required_parent_values(parent_root: ET.Element, parent_meta_url: str) -> dict[str, str]:
    parent_module_info = parent_root.find('./region/node/children/node[@id="ModuleInfo"]')
    if parent_module_info is None:
        raise ValueError(
            f"ModuleInfo node was not found in parent meta downloaded from '{parent_meta_url}'."
        )

    source_values: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        node = parent_module_info.find(f"./attribute[@id='{field}']")
        if node is None:
            raise ValueError(
                f"Required parent ModuleInfo attribute '{field}' is missing in meta downloaded from "
                f"'{parent_meta_url}'."
            )

        value = node.get("value", "")
        if not value.strip():
            raise ValueError(
                f"Required parent ModuleInfo attribute '{field}' has empty value in meta downloaded from "
                f"'{parent_meta_url}'."
            )

        source_values[field] = value

    return source_values


def ensure_target_dependency_node(target_root: ET.Element, target_meta_path: Path) -> None:
    target_dependency_node = target_root.find(
        './region/node/children/node[@id="Dependencies"]/children/node[@id="ModuleShortDesc"]'
    )
    if target_dependency_node is None:
        raise ValueError(
            f"Dependencies/ModuleShortDesc node was not found in target meta: '{target_meta_path}'."
        )

    for field in REQUIRED_FIELDS:
        target_attr = target_dependency_node.find(f"./attribute[@id='{field}']")
        if target_attr is None:
            raise ValueError(
                f"Target Dependencies/ModuleShortDesc attribute '{field}' is missing in "
                f"'{target_meta_path}'."
            )


def update_module_short_desc_block(block: str, source_values: dict[str, str], target_meta_path: Path) -> tuple[str, list[str]]:
    changed_fields: list[str] = []

    for field in REQUIRED_FIELDS:
        pattern = re.compile(
            rf'(<attribute id="{re.escape(field)}" type="[^"]+" value=")([^"]*)("/>)'
        )
        match = pattern.search(block)
        if match is None:
            raise ValueError(
                f"Target Dependencies/ModuleShortDesc attribute '{field}' is missing in '{target_meta_path}'."
            )

        current_value = match.group(2)
        new_value = escape(source_values[field], {'"': "&quot;"})
        if current_value != new_value:
            block = pattern.sub(rf"\g<1>{new_value}\g<3>", block, count=1)
            changed_fields.append(field)

    return block, changed_fields


def update_target_meta(target_raw: str, source_values: dict[str, str], target_meta_path: Path) -> tuple[str, list[str]]:
    match = MODULE_SHORT_DESC_PATTERN.search(target_raw)
    if match is None:
        raise ValueError(
            f"Dependencies/ModuleShortDesc node was not found in target meta: '{target_meta_path}'."
        )

    updated_block, changed_fields = update_module_short_desc_block(
        block=match.group(2),
        source_values=source_values,
        target_meta_path=target_meta_path,
    )
    updated_meta = f"{match.group(1)}{updated_block}{match.group(3)}"
    return (
        target_raw[: match.start()] + updated_meta + target_raw[match.end() :],
        changed_fields,
    )


def write_text_file(path: Path, text: str, has_bom: bool) -> None:
    encoding = "utf-8-sig" if has_bom else "utf-8"
    path.write_text(text, encoding=encoding, newline="")


def main() -> int:
    args = parse_args()
    target_meta_path = Path(args.target_meta_path).resolve()

    try:
        if not target_meta_path.exists():
            raise FileNotFoundError(f"Target meta.lsx was not found: '{target_meta_path}'.")

        parent_raw = download_parent_meta(args.parent_meta_url)
        target_raw, target_has_bom = load_text_file(target_meta_path)

        parent_root = parse_xml(parent_raw, args.parent_meta_url)
        target_root = parse_xml(target_raw, str(target_meta_path))

        source_values = get_required_parent_values(parent_root, args.parent_meta_url)
        ensure_target_dependency_node(target_root, target_meta_path)

        updated_target_raw, changed_fields = update_target_meta(
            target_raw=target_raw,
            source_values=source_values,
            target_meta_path=target_meta_path,
        )

        if not changed_fields:
            print("[sync-parent-meta.py] No changes needed. Target dependency data is already up to date.")
            return 0

        write_text_file(target_meta_path, updated_target_raw, target_has_bom)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print("[sync-parent-meta.py] Updated fields: " + ", ".join(changed_fields))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
