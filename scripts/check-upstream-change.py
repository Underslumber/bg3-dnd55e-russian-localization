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
DEFAULT_UPSTREAM_META_URL = (
    "https://raw.githubusercontent.com/Yoonmoonsik/dnd55e/main/"
    "Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/meta.lsx"
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
        "-UpstreamMetaUrl",
        "--upstream-meta-url",
        default=DEFAULT_UPSTREAM_META_URL,
        dest="upstream_meta_url",
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
        "-MetaDownloadPath",
        "--meta-download-path",
        default=".cache/upstream/meta.lsx",
        dest="meta_download_path",
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


def download_file(url: str, force: bool) -> tuple[bytes, dict[str, str], str]:
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


def decode_version64(value: int) -> str:
    return ".".join(
        str(part)
        for part in (
            (value >> 55) & 0x1FF,
            (value >> 47) & 0xFF,
            (value >> 31) & 0xFFFF,
            value & 0x7FFFFFFF,
        )
    )


def read_parent_version(payload: bytes, source_url: str) -> tuple[str, str]:
    root = ET.fromstring(payload.decode("utf-8-sig"))
    version_node = root.find(
        "./region/node/children/node[@id='ModuleInfo']/attribute[@id='Version64']"
    )
    if version_node is None:
        raise ValueError(f"Parent ModuleInfo/Version64 was not found in '{source_url}'.")

    raw_value = str(version_node.get("value") or "").strip()
    if not raw_value.isdigit():
        raise ValueError(f"Parent ModuleInfo/Version64 is invalid in '{source_url}': '{raw_value}'.")

    return raw_value, decode_version64(int(raw_value))


def main() -> int:
    args = parse_args()
    state_path = Path(args.state_path).resolve()
    download_path = Path(args.download_path).resolve()
    meta_download_path = Path(args.meta_download_path).resolve()
    output_path = Path(args.output_path).resolve()

    try:
        if not args.upstream_english_url.strip():
            raise ValueError("UpstreamEnglishUrl must not be empty.")
        if not args.upstream_meta_url.strip():
            raise ValueError("UpstreamMetaUrl must not be empty.")

        state = load_json(state_path)
        upstream_state = state.get("upstream") if isinstance(state.get("upstream"), dict) else {}
        release_state = state.get("release") if isinstance(state.get("release"), dict) else {}
        version_policy = (
            release_state.get("version_policy")
            if isinstance(release_state.get("version_policy"), dict)
            else {}
        )
        previous_sha256 = str(upstream_state.get("last_processed_sha256") or "").strip()
        previous_parent_version64 = str(version_policy.get("parent_version64") or "").strip()
        previous_parent_version = str(version_policy.get("parent_version") or "").strip()

        content, response_headers, resolved_url = download_file(
            url=args.upstream_english_url,
            force=args.force,
        )
        entry_count = validate_xml(content, resolved_url)
        current_sha256 = sha256_hex(content)

        parent_meta, _, resolved_meta_url = download_file(
            url=args.upstream_meta_url,
            force=args.force,
        )
        current_parent_version64, current_parent_version = read_parent_version(
            parent_meta,
            resolved_meta_url,
        )

        download_path.parent.mkdir(parents=True, exist_ok=True)
        download_path.write_bytes(content)
        meta_download_path.parent.mkdir(parents=True, exist_ok=True)
        meta_download_path.write_bytes(parent_meta)

        english_changed = current_sha256 != previous_sha256
        parent_version_changed = current_parent_version64 != previous_parent_version64

        report = {
            "checkedAt": get_now_iso(),
            "upstreamEnglishXmlUrl": resolved_url,
            "downloadPath": str(download_path),
            "outputPath": str(output_path),
            "statePath": str(state_path),
            "force": bool(args.force),
            "previousProcessedSha256": previous_sha256,
            "currentSha256": current_sha256,
            "englishChanged": english_changed,
            "parentMetaUrl": resolved_meta_url,
            "parentMetaDownloadPath": str(meta_download_path),
            "previousParentVersion64": previous_parent_version64,
            "previousParentVersion": previous_parent_version,
            "currentParentVersion64": current_parent_version64,
            "currentParentVersion": current_parent_version,
            "parentVersionChanged": parent_version_changed,
            "changed": english_changed or parent_version_changed,
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
        f"EnglishChanged={'yes' if report['englishChanged'] else 'no'}; "
        f"Parent={report['currentParentVersion']}; "
        f"ParentChanged={'yes' if report['parentVersionChanged'] else 'no'}; "
        f"Entries={report['entryCount']}."
    )
    print(f"[check-upstream-change.py] Report written to '{output_path}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
