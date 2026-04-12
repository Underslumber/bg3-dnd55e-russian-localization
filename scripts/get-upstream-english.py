#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_UPSTREAM_ENGLISH_URL = (
    "https://raw.githubusercontent.com/Yoonmoonsik/dnd55e/main/"
    "Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download upstream english.xml.")
    parser.add_argument(
        "-UpstreamEnglishUrl",
        "--upstream-english-url",
        default=DEFAULT_UPSTREAM_ENGLISH_URL,
        dest="upstream_english_url",
    )
    parser.add_argument(
        "-OutputPath",
        "--output-path",
        default=".cache/upstream/english.xml",
        dest="output_path",
    )
    parser.add_argument("-Force", "--force", action="store_true", dest="force")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output_path).resolve()

    try:
        if not args.upstream_english_url.strip():
            raise ValueError("UpstreamEnglishUrl must not be empty.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            args.upstream_english_url,
            headers=(
                {
                    "Cache-Control": "no-cache",
                    "User-Agent": "bg3-dnd55e-get-upstream-english/1.0",
                }
                if args.force
                else {"User-Agent": "bg3-dnd55e-get-upstream-english/1.0"}
            ),
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            output_path.write_bytes(response.read())

        root = ET.fromstring(output_path.read_text(encoding="utf-8-sig"))
        if root.tag != "contentList":
            raise ValueError(f"Downloaded file is not a valid BG3 localization XML: '{output_path}'.")

        content_count = len(root.findall("./content"))
        file_info = output_path.stat()
        updated_at = datetime.fromtimestamp(file_info.st_mtime, tz=timezone.utc).astimezone().isoformat()
    except (urllib.error.URLError, OSError, ET.ParseError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"[get-upstream-english.py] Saved upstream english.xml to '{output_path}'.")
    print(
        "[get-upstream-english.py] Entries: "
        f"{content_count}; Size: {file_info.st_size} bytes; Updated: {updated_at}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
