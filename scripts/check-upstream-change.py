#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_UPSTREAM_ENGLISH_URL = (
    "https://raw.githubusercontent.com/Yoonmoonsik/dnd55e/main/"
    "Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download upstream english.xml and compare its hash with tracked state.")
    parser.add_argument(
        "-UpstreamEnglishUrl",
        "--upstream-english-url",
        default=DEFAULT_UPSTREAM_ENGLISH_URL,
        dest="upstream_english_url",
    )
    parser.add_argument(
        "-StatePath",
        "--state-path",
        default=".github/autopilot/state.json",
        dest="state_path",
    )
    parser.add_argument(
        "-DownloadPath",
        "--download-path",
        default=".cache/upstream/english.xml",
        dest="download_path",
    )
    parser.add_argument(
        "-OutputPath",
        "--output-path",
        default="build/autopilot/upstream-check.json",
        dest="output_path",
    )
    parser.add_argument("-Force", "--force", action="store_true", dest="force")
    return parser.parse_args()


def get_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: '{path}'.")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_xml(payload: bytes, source_url: str) -> int:
    root = ET.fromstring(payload.decode("utf-8-sig"))
    if root.tag != "contentList":
        raise ValueError(f"Downloaded file is not a valid BG3 localization XML: '{source_url}'.")
    return len(root.findall("./content"))


def download_english_xml(url: str, force: bool) -> tuple[bytes, dict[str, str], str]:
    headers = {"User-Agent": "bg3-dnd55e-autopilot/1.0"}
    if force:
        headers["Cache-Control"] = "no-cache"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        content = response.read()
        response_headers = {
            "etag": response.headers.get("ETag", "") or "",
            "lastModified": response.headers.get("Last-Modified", "") or "",
            "contentType": response.headers.get("Content-Type", "") or "",
        }
        return content, response_headers, response.geturl()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state_path).resolve()
    download_path = Path(args.download_path).resolve()
    output_path = Path(args.output_path).resolve()

    try:
        if not args.upstream_english_url.strip():
            raise ValueError("UpstreamEnglishUrl must not be empty.")

        state = load_json(state_path)
        upstream_state = state.get("upstream") if isinstance(state.get("upstream"), dict) else {}
        previous_sha256 = str(upstream_state.get("last_processed_sha256") or "").strip()

        content, response_headers, resolved_url = download_english_xml(
            url=args.upstream_english_url,
            force=args.force,
        )
        entry_count = validate_xml(content, resolved_url)
        current_sha256 = sha256_hex(content)

        download_path.parent.mkdir(parents=True, exist_ok=True)
        download_path.write_bytes(content)

        report = {
            "checkedAt": get_now_iso(),
            "upstreamEnglishXmlUrl": resolved_url,
            "downloadPath": str(download_path),
            "outputPath": str(output_path),
            "statePath": str(state_path),
            "force": bool(args.force),
            "previousProcessedSha256": previous_sha256,
            "currentSha256": current_sha256,
            "changed": current_sha256 != previous_sha256,
            "entryCount": entry_count,
            "sizeBytes": len(content),
            "etag": response_headers["etag"],
            "lastModified": response_headers["lastModified"],
            "contentType": response_headers["contentType"],
        }
        write_json(output_path, report)
    except (OSError, ValueError, urllib.error.URLError, ET.ParseError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[check-upstream-change.py] "
        f"Upstream SHA256={report['currentSha256']}; Previous={previous_sha256 or 'n/a'}; "
        f"Changed={'yes' if report['changed'] else 'no'}; Entries={report['entryCount']}."
    )
    print(f"[check-upstream-change.py] Report written to '{output_path}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
