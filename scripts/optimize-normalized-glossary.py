#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_NORMALIZED_PATH = "glossary/glossary.normalized.json"
DEFAULT_OFFICIAL_PATH = "glossary/glossary.official.json"

MINOR_TITLE_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "without",
}


@dataclass(frozen=True)
class Candidate:
    english: str
    russian: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize glossary.normalized.json using official-first rules.")
    parser.add_argument(
        "-NormalizedPath",
        "--normalized-path",
        default=DEFAULT_NORMALIZED_PATH,
        dest="normalized_path",
    )
    parser.add_argument(
        "-OfficialPath",
        "--official-path",
        default=DEFAULT_OFFICIAL_PATH,
        dest="official_path",
    )
    return parser.parse_args()


def read_json_dict(path: Path) -> dict[str, str]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Glossary JSON was not found: '{resolved_path}'.")

    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Glossary JSON must contain an object at the root: '{resolved_path}'.")

    glossary: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError(f"Glossary JSON must contain only string-to-string pairs: '{resolved_path}'.")
        glossary[key] = value
    return glossary


def write_json_dict(path: Path, payload: dict[str, str]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_lookup_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def tokenize_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", text)


def is_title_like(text: str) -> bool:
    words = tokenize_words(text)
    if not words:
        return False

    for index, word in enumerate(words):
        normalized = word.replace("’", "'")
        if normalized.lower() in MINOR_TITLE_WORDS and index not in (0, len(words) - 1):
            if normalized != normalized.lower():
                return False
            continue

        first = normalized[0]
        rest = normalized[1:]
        if not first.isupper():
            return False
        if any(char.isupper() for char in rest):
            return False

    return True


def english_surface_score(text: str) -> tuple[int, int, int, int]:
    words = tokenize_words(text)
    title_like = 1 if is_title_like(text) else 0
    starts_upper = 1 if text[:1].isupper() else 0
    weird_internal_caps = 0 if re.search(r"[a-z][A-Z]", text) else 1
    return (title_like, starts_upper, weird_internal_caps, len(words))


def candidate_priority(candidate: Candidate, official: dict[str, str]) -> tuple[int, tuple[int, int, int, int], int, int, str, str]:
    official_value = official.get(candidate.english)
    exact_official_match = 1 if official_value == candidate.russian else 0
    exact_official_key = 1 if official_value is not None else 0
    english_score = english_surface_score(candidate.english)
    russian_length = len(candidate.russian.strip())
    english_length = len(candidate.english.strip())
    return (
        exact_official_match,
        english_score,
        exact_official_key,
        russian_length,
        candidate.english.lower(),
        candidate.russian.lower(),
    )


def choose_canonical_candidate(candidates: list[Candidate], official: dict[str, str]) -> Candidate:
    return max(candidates, key=lambda candidate: candidate_priority(candidate, official))


def sort_glossary(glossary: dict[str, str]) -> dict[str, str]:
    return dict(sorted(glossary.items(), key=lambda item: (item[0].lower(), item[0])))


def optimize_glossary(normalized: dict[str, str], official: dict[str, str]) -> tuple[dict[str, str], dict[str, Candidate]]:
    grouped: dict[str, list[Candidate]] = {}
    for english, russian in normalized.items():
        grouped.setdefault(normalize_lookup_key(english), []).append(Candidate(english=english, russian=russian))

    optimized: dict[str, str] = {}
    chosen_by_group: dict[str, Candidate] = {}
    for normalized_key, candidates in grouped.items():
        if len(candidates) == 1:
            chosen = candidates[0]
        else:
            chosen = choose_canonical_candidate(candidates, official)
        optimized[chosen.english] = chosen.russian
        chosen_by_group[normalized_key] = chosen

    return sort_glossary(optimized), chosen_by_group


def main() -> int:
    args = parse_args()

    try:
        normalized_path = Path(args.normalized_path).resolve()
        official_path = Path(args.official_path).resolve()

        normalized = read_json_dict(normalized_path)
        official = read_json_dict(official_path)
        optimized, _ = optimize_glossary(normalized=normalized, official=official)
        write_json_dict(normalized_path, optimized)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    removed_count = len(normalized) - len(optimized)
    print(
        "[optimize-normalized-glossary.py] "
        f"Optimized '{normalized_path}'. Before={len(normalized)} After={len(optimized)} Removed={removed_count}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
