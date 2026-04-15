#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


VALID_KINDS = ("translate", "review", "all")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare batched translation/review context for the translation-update skill.")
    parser.add_argument("-CandidatesPath", "--candidates-path", required=True, dest="candidates_path")
    parser.add_argument(
        "-OfficialGlossaryPath",
        "--official-glossary-path",
        default="glossary/glossary.official.json",
        dest="official_glossary_path",
    )
    parser.add_argument(
        "-SecondaryGlossaryPath",
        "--secondary-glossary-path",
        default="glossary/glossary.normalized.json",
        dest="secondary_glossary_path",
    )
    parser.add_argument("-Kind", "--kind", default="all", choices=VALID_KINDS, dest="kind")
    parser.add_argument("-Offset", "--offset", type=int, default=0, dest="offset")
    parser.add_argument("-Limit", "--limit", type=int, default=25, dest="limit")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"JSON file was not found: '{resolved_path}'.")
    return json.loads(resolved_path.read_text(encoding="utf-8"))


def read_glossary(path: Path) -> dict[str, str]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Glossary JSON root must be an object: '{path.resolve()}'.")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
        raise ValueError(f"Glossary JSON must contain only string-to-string pairs: '{path.resolve()}'.")
    return payload


def read_optional_glossary(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return read_glossary(path)


def normalize_multiline_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def glossary_term_match_spans(source_term: str, text: str) -> list[tuple[int, int]]:
    if not source_term or not text:
        return []

    escaped_term = re.escape(source_term)
    if re.search(r"[A-Za-z]", source_term):
        pattern = rf"(?<![A-Za-z]){escaped_term}(?![A-Za-z])"
        return [(match.start(), match.end()) for match in re.finditer(pattern, text, flags=re.IGNORECASE)]

    return [(match.start(), match.end()) for match in re.finditer(escaped_term, text, flags=re.IGNORECASE)]


def select_relevant_glossaries(
    official_glossary: dict[str, str],
    secondary_glossary: dict[str, str],
    texts: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    normalized_texts = [normalize_multiline_text(text) for text in texts if str(text).strip()]
    if not normalized_texts:
        return {}, {}

    term_candidates: list[dict[str, Any]] = []
    for source_term in official_glossary:
        term_candidates.append(
            {
                "term": source_term,
                "target": official_glossary[source_term],
                "source": "official",
                "priority": 0,
            }
        )
    for source_term in secondary_glossary:
        if source_term in official_glossary:
            continue
        term_candidates.append(
            {
                "term": source_term,
                "target": secondary_glossary[source_term],
                "source": "fallback",
                "priority": 1,
            }
        )

    ordered_candidates = sorted(
        term_candidates,
        key=lambda item: (-len(item["term"]), item["priority"], item["term"].lower(), item["term"]),
    )

    selected_terms: set[str] = set()
    for text in normalized_texts:
        chosen_terms: list[tuple[str, list[tuple[int, int]]]] = []
        for item in ordered_candidates:
            spans = glossary_term_match_spans(item["term"], text)
            if not spans:
                continue

            fully_covered = True
            for start, end in spans:
                if not any(
                    chosen_start <= start and end <= chosen_end
                    for _, chosen_spans in chosen_terms
                    for chosen_start, chosen_end in chosen_spans
                ):
                    fully_covered = False
                    break

            if fully_covered:
                continue

            chosen_terms.append((item["term"], spans))
            selected_terms.add(item["term"])

    selected_official: dict[str, str] = {}
    selected_fallback: dict[str, str] = {}
    for item in ordered_candidates:
        source_term = item["term"]
        if source_term not in selected_terms:
            continue
        if item["source"] == "official":
            selected_official[source_term] = item["target"]
        else:
            selected_fallback[source_term] = item["target"]

    return selected_official, selected_fallback


def get_required_section(candidates: dict[str, Any], field: str) -> list[dict[str, Any]]:
    value = candidates.get(field) or []
    if not isinstance(value, list):
        raise ValueError(f"Candidates field '{field}' must be an array.")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Candidates field '{field}' must contain only objects.")
    return [dict(item) for item in value]


def build_translate_units(candidates: dict[str, Any]) -> list[dict[str, Any]]:
    units_by_english: dict[str, dict[str, Any]] = {}

    for entry in get_required_section(candidates, "adds"):
        content_uid = str(entry.get("contentuid", "")).strip()
        version = str(entry.get("version", "")).strip()
        english_text = normalize_multiline_text(entry.get("englishText", ""))
        if not content_uid:
            raise ValueError("Each add candidate must contain non-empty 'contentuid'.")
        if not version:
            raise ValueError(f"Add candidate '{content_uid}' must contain non-empty 'version'.")
        if not english_text.strip():
            raise ValueError(f"Add candidate '{content_uid}' must contain non-empty 'englishText'.")

        unit = units_by_english.setdefault(
            english_text,
            {
                "unitId": f"translate-{len(units_by_english) + 1:05d}",
                "englishText": english_text,
                "targets": [],
            },
        )
        unit["targets"].append(
            {
                "contentuid": content_uid,
                "version": version,
                "section": "adds",
            }
        )

    return list(units_by_english.values())


def build_review_units(candidates: dict[str, Any]) -> list[dict[str, Any]]:
    units_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for entry in get_required_section(candidates, "updates"):
        content_uid = str(entry.get("contentuid", "")).strip()
        version = str(entry.get("version", "")).strip()
        english_text = normalize_multiline_text(entry.get("englishText", ""))
        current_russian_text = normalize_multiline_text(entry.get("currentRussianText", ""))

        if not content_uid:
            raise ValueError("Each update candidate must contain non-empty 'contentuid'.")
        if not version:
            raise ValueError(f"Update candidate '{content_uid}' must contain non-empty 'version'.")
        if not english_text.strip():
            raise ValueError(f"Update candidate '{content_uid}' must contain non-empty 'englishText'.")

        dedupe_key = (english_text, current_russian_text)
        unit = units_by_key.setdefault(
            dedupe_key,
            {
                "unitId": f"review-{len(units_by_key) + 1:05d}",
                "englishText": english_text,
                "currentRussianText": current_russian_text,
                "targets": [],
            },
        )
        unit["targets"].append(
            {
                "contentuid": content_uid,
                "version": version,
                "section": "updates",
            }
        )

    return list(units_by_key.values())


def build_deletes(candidates: dict[str, Any]) -> list[dict[str, str]]:
    deletes: list[dict[str, str]] = []
    seen_content_uids: set[str] = set()
    for entry in get_required_section(candidates, "deletes"):
        content_uid = str(entry.get("contentuid", "")).strip()
        if not content_uid:
            raise ValueError("Each delete candidate must contain non-empty 'contentuid'.")
        if content_uid in seen_content_uids:
            raise ValueError(f"Delete candidates contain duplicate contentuid '{content_uid}'.")
        seen_content_uids.add(content_uid)
        deletes.append({"contentuid": content_uid})
    return deletes


def slice_units(
    *,
    kind: str,
    offset: int,
    limit: int,
    translate_units: list[dict[str, Any]],
    review_units: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, bool, int | None]:
    combined_units: list[tuple[str, dict[str, Any]]] = []
    if kind in {"translate", "all"}:
        combined_units.extend(("translate", unit) for unit in translate_units)
    if kind in {"review", "all"}:
        combined_units.extend(("review", unit) for unit in review_units)

    selected_items = combined_units[offset : offset + limit]
    selected_translate_units = [unit for unit_kind, unit in selected_items if unit_kind == "translate"]
    selected_review_units = [unit for unit_kind, unit in selected_items if unit_kind == "review"]
    next_offset = offset + len(selected_items)
    has_more = next_offset < len(combined_units)
    return selected_translate_units, selected_review_units, len(combined_units), has_more, (
        next_offset if has_more else None
    )


def main() -> int:
    args = parse_args()

    try:
        if args.offset < 0:
            raise ValueError("Offset must be greater than or equal to 0.")
        if args.limit <= 0:
            raise ValueError("Limit must be greater than 0.")

        candidates_path = Path(args.candidates_path).resolve()
        official_glossary_path = Path(args.official_glossary_path).resolve()
        secondary_glossary_path = Path(args.secondary_glossary_path).resolve()

        candidates = read_json(candidates_path)
        if not isinstance(candidates, dict):
            raise ValueError("Candidates JSON root must be an object.")

        official_glossary = read_glossary(official_glossary_path)
        secondary_glossary = read_optional_glossary(secondary_glossary_path)

        translate_units = build_translate_units(candidates)
        review_units = build_review_units(candidates)
        deletes = build_deletes(candidates)
        selected_translate_units, selected_review_units, total_units, has_more, next_offset = slice_units(
            kind=args.kind,
            offset=args.offset,
            limit=args.limit,
            translate_units=translate_units,
            review_units=review_units,
        )

        selected_texts = [unit["englishText"] for unit in selected_translate_units]
        selected_texts.extend(unit["englishText"] for unit in selected_review_units)
        selected_official_glossary, selected_fallback_glossary = select_relevant_glossaries(
            official_glossary=official_glossary,
            secondary_glossary=secondary_glossary,
            texts=selected_texts,
        )

        selected_targets = sum(len(unit["targets"]) for unit in selected_translate_units)
        selected_targets += sum(len(unit["targets"]) for unit in selected_review_units)
        payload = {
            "mode": str(candidates.get("mode") or ""),
            "kind": args.kind,
            "stats": {
                "offset": args.offset,
                "limit": args.limit,
                "totalTranslateUnits": len(translate_units),
                "totalReviewUnits": len(review_units),
                "totalDeletes": len(deletes),
                "totalUnits": total_units,
                "selectedTranslateUnits": len(selected_translate_units),
                "selectedReviewUnits": len(selected_review_units),
                "selectedUnits": len(selected_translate_units) + len(selected_review_units),
                "selectedTargets": selected_targets,
                "selectedEnglishTextChars": sum(len(text) for text in selected_texts),
            },
            "hasMore": has_more,
            "nextOffset": next_offset,
            "translateUnits": selected_translate_units,
            "reviewUnits": selected_review_units,
            "deletes": deletes,
            "officialGlossary": selected_official_glossary,
            "fallbackGlossary": selected_fallback_glossary,
        }
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
