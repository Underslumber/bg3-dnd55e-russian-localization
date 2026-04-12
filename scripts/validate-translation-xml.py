#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate BG3 localization XML.")
    parser.add_argument("-XmlPath", "--xml-path", required=True, dest="xml_path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    xml_path = Path(args.xml_path).resolve()

    try:
        if not xml_path.exists():
            raise FileNotFoundError(f"XML file was not found: '{xml_path}'.")

        root = ET.fromstring(xml_path.read_text(encoding="utf-8-sig"))
        if root.tag != "contentList":
            raise ValueError(f"XML validation failed: missing '/contentList' in '{xml_path}'.")

        content_nodes = root.findall("./content")
        if not content_nodes:
            raise ValueError(
                f"XML validation failed: no '/contentList/content' entries found in '{xml_path}'."
            )

        seen: set[str] = set()
        for node in content_nodes:
            content_uid = node.get("contentuid", "")
            if not content_uid.strip():
                raise ValueError(
                    f"XML validation failed: found content node without 'contentuid' in '{xml_path}'."
                )

            if content_uid in seen:
                raise ValueError(
                    f"XML validation failed: duplicate contentuid '{content_uid}' in '{xml_path}'."
                )
            seen.add(content_uid)

            version = node.get("version", "")
            if not version.strip():
                raise ValueError(
                    f"XML validation failed: contentuid '{content_uid}' has empty 'version' in '{xml_path}'."
                )
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"[validate-translation-xml.py] XML is valid: '{xml_path}'. Entries={len(content_nodes)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
