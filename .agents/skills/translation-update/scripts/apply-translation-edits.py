#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape


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


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").exists() and (candidate / "scripts" / "validate-translation-xml.py").exists():
            return candidate
    raise FileNotFoundError("Repository root with AGENTS.md and scripts/validate-translation-xml.py was not found.")


def read_xml_document(path: Path) -> tuple[ET.ElementTree, str, str]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"XML file was not found: '{resolved_path}'.")

    raw_text = resolved_path.read_text(encoding="utf-8-sig")
    xml_declaration = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
    declaration_match = re.match(r"\s*(<\?xml[^>]+\?>)", raw_text)
    if declaration_match:
        xml_declaration = declaration_match.group(1)

    opening_tag_match = re.search(r"<contentList\b[^>]*>", raw_text)
    if not opening_tag_match:
        raise ValueError(f"XML file does not contain opening '<contentList>' tag: '{resolved_path}'.")
    content_list_opening_tag = opening_tag_match.group(0)

    root = ET.fromstring(raw_text)
    if root.tag != "contentList":
        raise ValueError(f"XML file does not contain '/contentList': '{resolved_path}'.")
    return ET.ElementTree(root), xml_declaration, content_list_opening_tag


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


def serialize_content_node(node: ET.Element) -> str:
    content_uid = node.get("contentuid", "")
    version = node.get("version", "")
    text = escape(node.text or "")
    return f'  <content contentuid="{escape(content_uid)}" version="{escape(version)}">{text}</content>'


def write_xml(path: Path, xml_tree: ET.ElementTree, xml_declaration: str, content_list_opening_tag: str) -> None:
    indent_xml(xml_tree.getroot())
    content_lines = [serialize_content_node(node) for node in xml_tree.getroot().findall("./content")]
    xml_text = "\n".join([xml_declaration, content_list_opening_tag, *content_lines, "</contentList>", ""])
    path.write_bytes(b"\xef\xbb\xbf" + xml_text.encode("utf-8"))


def run_validation(xml_path: Path) -> None:
    repo_root = find_repo_root(Path(__file__).resolve().parent)
    validate_script_path = repo_root / "scripts" / "validate-translation-xml.py"
    result = subprocess.run(
        [sys.executable, str(validate_script_path), "--xml-path", str(xml_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=str(repo_root),
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "XML validation failed.")


def get_required_list(payload: dict[str, object], field: str) -> list[dict[str, object]]:
    value = payload.get(field) or []
    if not isinstance(value, list):
        raise ValueError(f"Edits field '{field}' must be an array.")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Edits field '{field}' must contain only objects.")
    return [dict(item) for item in value]


def main() -> int:
    args = parse_args()
    russian_path = Path(args.russian_path).resolve()
    temporary_russian_path = russian_path.with_name(russian_path.name + ".tmp")
    edits_path = Path(args.edits_path).resolve()

    try:
        if not edits_path.exists():
            raise FileNotFoundError(f"Edits file was not found: '{edits_path}'.")

        edits = json.loads(edits_path.read_text(encoding="utf-8"))
        if not isinstance(edits, dict):
            raise ValueError("Edits JSON root must be an object.")

        updates = get_required_list(edits, "updates")
        adds = get_required_list(edits, "adds")
        deletes = get_required_list(edits, "deletes")

        if temporary_russian_path.exists():
            temporary_russian_path.unlink()
        temporary_russian_path.write_bytes(russian_path.read_bytes())

        russian_document, xml_declaration, content_list_opening_tag = read_xml_document(temporary_russian_path)
        content_list_node = russian_document.getroot()
        node_map = get_content_node_map(russian_document)
        updated_entries: list[str] = []
        added_entries: list[str] = []
        deleted_entries: list[str] = []
        seen_edit_content_uids: set[str] = set()

        for edit in updates:
            content_uid = str(edit.get("contentuid", "")).strip()
            if not content_uid:
                raise ValueError("Each update entry must contain non-empty 'contentuid'.")
            assert_unique_edit_content_uid(seen_edit_content_uids, content_uid, "updates")

        for edit in adds:
            content_uid = str(edit.get("contentuid", "")).strip()
            if not content_uid:
                raise ValueError("Each add entry must contain non-empty 'contentuid'.")
            assert_unique_edit_content_uid(seen_edit_content_uids, content_uid, "adds")

        for edit in deletes:
            content_uid = str(edit.get("contentuid", "")).strip()
            if not content_uid:
                raise ValueError("Each delete entry must contain non-empty 'contentuid'.")
            assert_unique_edit_content_uid(seen_edit_content_uids, content_uid, "deletes")

        if not updates and not adds and not deletes:
            temporary_russian_path.unlink()
            print("[translation-update:apply] No edits requested. Original russian.xml left unchanged.")
            return 0

        for edit in updates:
            content_uid = str(edit.get("contentuid", "")).strip()
            if content_uid not in node_map:
                raise ValueError(f"Target russian.xml does not contain contentuid '{content_uid}' for update.")

            node = node_map[content_uid]
            version = str(edit.get("version", "") or "").strip()
            if version:
                node.set("version", version)

            if "text" in edit:
                text = str(edit.get("text", ""))
                if not text.strip():
                    raise ValueError(f"Update entry '{content_uid}' must contain non-empty 'text' when provided.")
                node.text = text

            updated_entries.append(content_uid)

        for edit in adds:
            content_uid = str(edit.get("contentuid", "")).strip()
            version = str(edit.get("version", "")).strip()
            text = str(edit.get("text", ""))

            if content_uid in node_map:
                raise ValueError(
                    f"Target russian.xml already contains contentuid '{content_uid}'; use 'updates' instead of 'adds'."
                )
            if not version:
                raise ValueError(f"Add entry '{content_uid}' must contain non-empty 'version'.")
            if not text.strip():
                raise ValueError(f"Add entry '{content_uid}' must contain non-empty 'text'.")

            new_node = ET.Element("content", {"contentuid": content_uid, "version": version})
            new_node.text = text
            content_list_node.append(new_node)
            node_map[content_uid] = new_node
            added_entries.append(content_uid)

        for edit in deletes:
            content_uid = str(edit.get("contentuid", "")).strip()
            if content_uid not in node_map:
                raise ValueError(f"Target russian.xml does not contain contentuid '{content_uid}' for delete.")

            node = node_map.pop(content_uid)
            content_list_node.remove(node)
            deleted_entries.append(content_uid)

        write_xml(temporary_russian_path, russian_document, xml_declaration, content_list_opening_tag)
        run_validation(temporary_russian_path)
        russian_path.write_bytes(temporary_russian_path.read_bytes())
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        if temporary_russian_path.exists():
            temporary_russian_path.unlink()

    print(
        f"[translation-update:apply] Updated entries: {len(updated_entries)}; "
        f"Added entries: {len(added_entries)}; Deleted entries: {len(deleted_entries)}."
    )
    if updated_entries:
        print("[translation-update:apply] Updated contentuid: " + ", ".join(updated_entries))
    if added_entries:
        print("[translation-update:apply] Added contentuid: " + ", ".join(added_entries))
    if deleted_entries:
        print("[translation-update:apply] Deleted contentuid: " + ", ".join(deleted_entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
