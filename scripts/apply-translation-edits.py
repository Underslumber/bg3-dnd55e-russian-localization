#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply prepared translation edits to russian.xml.")
    parser.add_argument(
        "-RussianPath",
        "--russian-path",
        default="Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
        dest="russian_path",
    )
    parser.add_argument("-EditsPath", "--edits-path", required=True, dest="edits_path")
    return parser.parse_args()


def read_xml_document(path: Path) -> ET.ElementTree:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"XML file was not found: '{resolved_path}'.")

    root = ET.fromstring(resolved_path.read_text(encoding="utf-8-sig"))
    if root.tag != "contentList":
        raise ValueError(f"XML file does not contain '/contentList': '{resolved_path}'.")
    return ET.ElementTree(root)


def get_content_node_map(xml_tree: ET.ElementTree) -> dict[str, ET.Element]:
    mapping: dict[str, ET.Element] = {}
    for node in xml_tree.getroot().findall("./content"):
        content_uid = node.get("contentuid", "")
        if not content_uid.strip():
            continue
        if content_uid in mapping:
            raise ValueError(f"Duplicate contentuid found in target XML: '{content_uid}'.")
        mapping[content_uid] = node
    return mapping


def assert_unique_edit_content_uid(seen: set[str], content_uid: str, section: str) -> None:
    if content_uid in seen:
        raise ValueError(f"Edits file contains duplicate contentuid '{content_uid}' in '{section}'.")
    seen.add(content_uid)


def indent_xml(element: ET.Element, level: int = 0) -> None:
    indent = "\n" + level * "  "
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "
        for child in element:
            indent_xml(child, level + 1)
        if not element[-1].tail or not element[-1].tail.strip():
            element[-1].tail = indent
    elif level and (not element.tail or not element.tail.strip()):
        element.tail = indent


def write_xml(path: Path, xml_tree: ET.ElementTree) -> None:
    indent_xml(xml_tree.getroot())
    xml_bytes = ET.tostring(xml_tree.getroot(), encoding="utf-8", xml_declaration=True, short_empty_elements=True)
    path.write_bytes(b"\xef\xbb\xbf" + xml_bytes)


def run_validation(xml_path: Path) -> None:
    validate_script_path = Path(__file__).with_name("validate-translation-xml.py")
    if not validate_script_path.exists():
        raise FileNotFoundError(f"Validation script was not found: '{validate_script_path}'.")

    result = subprocess.run(
        [sys.executable, str(validate_script_path), "--xml-path", str(xml_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "XML validation failed.")


def main() -> int:
    args = parse_args()
    russian_path = Path(args.russian_path).resolve()
    temporary_russian_path = russian_path.with_name(russian_path.name + ".tmp")
    edits_path = Path(args.edits_path).resolve()

    try:
        russian_document = read_xml_document(russian_path)
        if temporary_russian_path.exists():
            temporary_russian_path.unlink()
        temporary_russian_path.write_bytes(russian_path.read_bytes())
        russian_document = read_xml_document(temporary_russian_path)

        if not edits_path.exists():
            raise FileNotFoundError(f"Edits file was not found: '{edits_path}'.")

        edits = json.loads(edits_path.read_text(encoding="utf-8"))
        content_list_node = russian_document.getroot()
        node_map = get_content_node_map(russian_document)
        updated_entries: list[str] = []
        added_entries: list[str] = []
        seen_edit_content_uids: set[str] = set()

        updates = list(edits.get("updates") or [])
        adds = list(edits.get("adds") or [])

        for edit in updates:
            content_uid = str(edit.get("contentuid", ""))
            if not content_uid.strip():
                raise ValueError("Each update entry must contain non-empty 'contentuid'.")

            assert_unique_edit_content_uid(seen_edit_content_uids, content_uid, "updates")

            if content_uid not in node_map:
                raise ValueError(f"Target russian.xml does not contain contentuid '{content_uid}' for update.")

            node = node_map[content_uid]
            version = str(edit.get("version", "") or "")
            if version.strip():
                node.set("version", version)

            if "text" in edit:
                text = str(edit.get("text", ""))
                if not text.strip():
                    raise ValueError(f"Update entry '{content_uid}' must contain non-empty 'text' when provided.")
                node.text = text

            updated_entries.append(content_uid)

        if not updates and not adds:
            if temporary_russian_path.exists():
                temporary_russian_path.unlink()
            print("[apply-translation-edits.py] No edits requested. Original russian.xml left unchanged.")
            return 0

        for edit in adds:
            content_uid = str(edit.get("contentuid", ""))
            version = str(edit.get("version", ""))
            text = str(edit.get("text", ""))

            if not content_uid.strip():
                raise ValueError("Each add entry must contain non-empty 'contentuid'.")
            assert_unique_edit_content_uid(seen_edit_content_uids, content_uid, "adds")
            if content_uid in node_map:
                raise ValueError(
                    f"Target russian.xml already contains contentuid '{content_uid}'; use 'updates' instead of 'adds'."
                )
            if not version.strip():
                raise ValueError(f"Add entry '{content_uid}' must contain non-empty 'version'.")
            if not text.strip():
                raise ValueError(f"Add entry '{content_uid}' must contain non-empty 'text'.")

            new_node = ET.Element("content", {"contentuid": content_uid, "version": version})
            new_node.text = text
            content_list_node.append(new_node)
            node_map[content_uid] = new_node
            added_entries.append(content_uid)

        write_xml(temporary_russian_path, russian_document)
        run_validation(temporary_russian_path)
        russian_path.write_bytes(temporary_russian_path.read_bytes())
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        if temporary_russian_path.exists():
            temporary_russian_path.unlink()

    print(
        f"[apply-translation-edits.py] Updated entries: {len(updated_entries)}; "
        f"Added entries: {len(added_entries)}."
    )
    if updated_entries:
        print("[apply-translation-edits.py] Updated contentuid: " + ", ".join(updated_entries))
    if added_entries:
        print("[apply-translation-edits.py] Added contentuid: " + ", ".join(added_entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
