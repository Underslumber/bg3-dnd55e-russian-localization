#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib import parse
from urllib import error, request


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_GENERATION_URL = "https://openrouter.ai/api/v1/generation"
DEFAULT_CANDIDATES_PATH = "build/translation-diff/candidates.json"
DEFAULT_OFFICIAL_GLOSSARY_PATH = "glossary/glossary.official.json"
DEFAULT_SECONDARY_GLOSSARY_PATH = "glossary/glossary.normalized.json"
DEFAULT_USAGE_REPORT_PATH = "build/translation-diff/openrouter-usage.json"
DEFAULT_BATCH_SIZE = 20
DEFAULT_MAX_BATCH_CHARS = 6000
DEFAULT_RETRIES = 3
FREE_DEFAULT_BATCH_SIZE = 10
FREE_DEFAULT_MAX_BATCH_CHARS = 3000
FREE_DEFAULT_RETRIES = 4
REQUEST_TIMEOUT_SECONDS = 120

SYSTEM_PROMPT = (
    "You are a professional video game translator.\n\n"
    "Context: Baldur's Gate 3, DnD 5.5e terminology.\n\n"
    "You receive a JSON array of objects:\n"
    '[{"id":"...","english":"..."}]\n\n'
    'Translate each "english" value into Russian.\n\n'
    "Rules:\n"
    '- Return the same "id" unchanged.\n'
    "- Output one result for every input object.\n"
    '- Do not include the original English text in the output.\n'
    "- Use the glossary as a strict source of truth.\n"
    "- If an official glossary term appears, use its official translation exactly.\n"
    "- Use the secondary glossary only as a fallback when no official glossary rule applies.\n"
    "- Follow the existing Russian localization style used by this mod.\n"
    "- Translate names, features, classes, and subclass titles as polished in-game UI text, not as literal dictionary glosses.\n"
    '- If the source starts with "Level N:", the result must start with "Уровень N:".\n'
    "- Translate text inside tags too; do not leave words like Checks untranslated.\n"
    "- Do not leave English terms untranslated unless they are placeholders or tag attributes.\n"
    "- Prefer established BG3-style terminology such as спасбросок, атака по возможности, бонус мастерства, владение, очки здоровья.\n"
    "- Preserve placeholders, numbers, variables, XML/HTML tags, LSTag tags, bracketed values like [1], and line breaks.\n"
    "- Keep terminology consistent.\n"
    "- If 'old_ru' is provided in an input object, it is the previous translation for reference only; produce a fresh, improved translation — do not copy it verbatim.\n"
    "- Return only valid JSON.\n\n"
    "Glossary format:\n"
    "- The prompt may contain `Official Glossary` and `Secondary Glossary` blocks.\n"
    "- Each block uses plain text lines in the form `English => Russian`.\n"
    "- Official rules have priority over secondary rules.\n"
    "- Use each rule as an exact terminology mapping when the English source term appears.\n\n"
    'Output format:\n{"translations":[{"id":"...","ru":"..."}]}'
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill translation candidates via OpenRouter.")
    parser.add_argument(
        "-CandidatesPath",
        "--candidates-path",
        default=DEFAULT_CANDIDATES_PATH,
        dest="candidates_path",
        help="Path to build/translation-diff/candidates.json.",
    )
    parser.add_argument(
        "-GlossaryPath",
        "--glossary-path",
        default="",
        dest="glossary_path",
        help="Legacy single-glossary path. If set, dual-glossary mode is disabled and only this dictionary is used.",
    )
    parser.add_argument(
        "-OfficialGlossaryPath",
        "--official-glossary-path",
        default=DEFAULT_OFFICIAL_GLOSSARY_PATH,
        dest="official_glossary_path",
        help="Path to the primary official glossary JSON dictionary.",
    )
    parser.add_argument(
        "-SecondaryGlossaryPath",
        "--secondary-glossary-path",
        default=DEFAULT_SECONDARY_GLOSSARY_PATH,
        dest="secondary_glossary_path",
        help="Path to the secondary fallback glossary JSON dictionary.",
    )
    parser.add_argument(
        "-EnglishPath",
        "--english-path",
        default=".cache/upstream/english.xml",
        dest="english_path",
        help="Path to upstream English localization XML used for exact-match translation memory.",
    )
    parser.add_argument(
        "-RussianPath",
        "--russian-path",
        default="Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
        dest="russian_path",
        help="Path to current Russian localization XML used for exact-match translation memory.",
    )
    parser.add_argument(
        "-ReferenceRussianPath",
        "--reference-russian-path",
        default="",
        dest="reference_russian_path",
        help="Optional path to a reference Russian XML whose matching contentuid values should be reused directly.",
    )
    parser.add_argument(
        "-OutputPath",
        "--output-path",
        default="",
        dest="output_path",
        help="Where to write the filled candidates JSON. Defaults to in-place update.",
    )
    parser.add_argument(
        "-UsageReportPath",
        "--usage-report-path",
        default=DEFAULT_USAGE_REPORT_PATH,
        dest="usage_report_path",
        help="Where to write the OpenRouter usage/cost JSON report.",
    )
    parser.add_argument(
        "-BatchSize",
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        dest="batch_size",
        help="Maximum number of representative strings per API request.",
    )
    parser.add_argument(
        "-MaxBatchChars",
        "--max-batch-chars",
        type=int,
        default=DEFAULT_MAX_BATCH_CHARS,
        dest="max_batch_chars",
        help="Maximum total English characters per batch.",
    )
    parser.add_argument(
        "-Retries",
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        dest="retries",
        help="Retry count per failed batch request.",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        dest="include_existing",
        help="Also retranslate entries that already contain non-empty text.",
    )
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'").strip('"')


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: '{name}'.")
    return value


def read_json(path: Path) -> Any:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"JSON file was not found: '{resolved_path}'.")
    return json.loads(resolved_path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_glossary(path: Path) -> dict[str, str]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Glossary JSON root must be an object: '{path.resolve()}'.")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
        raise ValueError(f"Glossary JSON must contain only string-to-string pairs: '{path.resolve()}'.")
    return payload


def read_optional_glossary(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    if not path.exists():
        return {}
    return read_glossary(path)


def merge_glossaries(official_glossary: dict[str, str], secondary_glossary: dict[str, str]) -> dict[str, str]:
    merged = dict(official_glossary)
    for key, value in secondary_glossary.items():
        if key not in merged:
            merged[key] = value
    return merged


def format_usd(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.000001'))} USD"


def parse_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def is_free_model(model: str) -> bool:
    return model.strip().lower().endswith(":free")


def zero_pricing() -> dict[str, Decimal]:
    return {
        "prompt": Decimal("0"),
        "completion": Decimal("0"),
        "request": Decimal("0"),
        "internal_reasoning": Decimal("0"),
    }


def compute_effective_runtime_settings(
    *,
    is_free: bool,
    batch_size: int,
    max_batch_chars: int,
    retries: int,
) -> dict[str, int]:
    effective_batch_size = batch_size
    effective_max_batch_chars = max_batch_chars
    effective_retries = retries

    if is_free:
        if batch_size == DEFAULT_BATCH_SIZE:
            effective_batch_size = FREE_DEFAULT_BATCH_SIZE
        if max_batch_chars == DEFAULT_MAX_BATCH_CHARS:
            effective_max_batch_chars = FREE_DEFAULT_MAX_BATCH_CHARS
        if retries == DEFAULT_RETRIES:
            effective_retries = FREE_DEFAULT_RETRIES

    return {
        "batch_size": effective_batch_size,
        "max_batch_chars": effective_max_batch_chars,
        "retries": effective_retries,
    }


def compute_retry_sleep_seconds(attempt: int, *, is_free: bool) -> int:
    if is_free:
        return min(4 * attempt, 12)
    return min(2 * attempt, 6)


def normalize_openrouter_error_message(raw_message: str, *, model: str, is_free: bool) -> str:
    normalized = " ".join(str(raw_message or "").split())
    if not is_free:
        return normalized

    lower = normalized.lower()
    free_issue_fragments = (
        "429",
        "rate limit",
        "too many requests",
        "quota",
        "capacity",
        "provider unavailable",
        "no provider",
        "temporarily unavailable",
        "temporary overload",
        "service unavailable",
    )
    if any(fragment in lower for fragment in free_issue_fragments):
        return (
            f"Free-модель '{model}' недоступна или упёрлась в лимит. "
            "Попробуйте позже или смените OPENROUTER_MODEL. "
            f"Детали: {normalized}"
        )
    return normalized


def openrouter_request(
    url: str,
    *,
    method: str,
    api_key: str,
    payload: Any | None = None,
) -> dict[str, Any]:
    request_data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "bg3-dnd55e-russian-localization/1.0",
    }
    if payload is not None:
        request_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = request.Request(
        url,
        data=request_data,
        headers=headers,
        method=method,
    )

    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body_text = ""
        detail = f"HTTP {exc.code} {exc.reason}"
        if body_text:
            detail = f"{detail}; body: {body_text}"
        raise RuntimeError(f"OpenRouter API request failed: {detail}") from exc


def normalize_multiline_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def glossary_term_matches_text(source_term: str, text: str) -> bool:
    if not source_term or not text:
        return False

    escaped_term = re.escape(source_term)
    if re.search(r"[A-Za-z]", source_term):
        pattern = rf"(?<![A-Za-z]){escaped_term}(?![A-Za-z])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None

    return source_term.lower() in text.lower()


def glossary_term_match_spans(source_term: str, text: str) -> list[tuple[int, int]]:
    if not source_term or not text:
        return []

    escaped_term = re.escape(source_term)
    if re.search(r"[A-Za-z]", source_term):
        pattern = rf"(?<![A-Za-z]){escaped_term}(?![A-Za-z])"
        return [(match.start(), match.end()) for match in re.finditer(pattern, text, flags=re.IGNORECASE)]

    return [(match.start(), match.end()) for match in re.finditer(escaped_term, text, flags=re.IGNORECASE)]


def read_localization_entries(path: Path) -> dict[str, dict[str, str]]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Localization XML was not found: '{resolved_path}'.")

    root = ET.fromstring(resolved_path.read_text(encoding="utf-8-sig"))
    if root.tag != "contentList":
        raise ValueError(f"Localization XML does not contain '/contentList': '{resolved_path}'.")

    entries: dict[str, dict[str, str]] = {}
    for node in root.findall("./content"):
        content_uid = str(node.get("contentuid", "")).strip()
        if not content_uid:
            continue

        entries[content_uid] = {
            "contentuid": content_uid,
            "version": str(node.get("version", "") or ""),
            "text": normalize_multiline_text(node.text or ""),
        }
    return entries


def build_exact_translation_memory(english_path: Path, russian_path: Path) -> dict[str, str]:
    english_entries = read_localization_entries(english_path)
    russian_entries = read_localization_entries(russian_path)
    variants_by_english: dict[str, set[str]] = collections.defaultdict(set)

    for content_uid, english_entry in english_entries.items():
        russian_entry = russian_entries.get(content_uid)
        if russian_entry is None:
            continue

        english_text = normalize_multiline_text(english_entry["text"]).strip()
        russian_text = normalize_multiline_text(russian_entry["text"]).strip()
        if not english_text or not russian_text:
            continue

        variants_by_english[english_text].add(russian_text)

    translation_memory: dict[str, str] = {}
    for english_text, variants in variants_by_english.items():
        if len(variants) == 1:
            translation_memory[english_text] = next(iter(variants))
    return translation_memory


def build_reference_translation_map(reference_russian_path: Path) -> dict[str, str]:
    reference_entries = read_localization_entries(reference_russian_path)
    return {
        content_uid: entry["text"]
        for content_uid, entry in reference_entries.items()
        if normalize_multiline_text(entry["text"]).strip()
    }


def select_relevant_glossary(glossary: dict[str, str], texts: list[str]) -> dict[str, str]:
    normalized_texts = [normalize_multiline_text(text) for text in texts if text]
    if not normalized_texts:
        return {}

    selected_terms: set[str] = set()
    sorted_terms = sorted(glossary.keys(), key=len, reverse=True)

    for text in normalized_texts:
        matched_terms: list[tuple[str, list[tuple[int, int]]]] = []
        for source_term in sorted_terms:
            spans = glossary_term_match_spans(source_term, text)
            if spans:
                matched_terms.append((source_term, spans))

        chosen_terms: list[tuple[str, list[tuple[int, int]]]] = []
        for source_term, spans in matched_terms:
            fully_covered = True
            for start, end in spans:
                if not any(
                    chosen_start <= start and end <= chosen_end
                    for _, chosen_spans in chosen_terms
                    for chosen_start, chosen_end in chosen_spans
                ):
                    fully_covered = False
                    break

            if not fully_covered:
                chosen_terms.append((source_term, spans))
                selected_terms.add(source_term)

    relevant: dict[str, str] = {}
    for source_term in sorted(selected_terms, key=lambda value: (-len(value), value.lower(), value)):
        relevant[source_term] = glossary[source_term]
    return relevant


def get_relevant_glossary_terms(glossary: dict[str, str], english_text: str) -> dict[str, str]:
    return select_relevant_glossary(glossary, [english_text])


def replace_visible_glossary_terms(translated_text: str, relevant_glossary: dict[str, str]) -> str:
    parts = re.split(r"(<[^>]+>)", translated_text)
    ordered_terms = sorted(relevant_glossary.items(), key=lambda item: len(item[0]), reverse=True)

    for index, part in enumerate(parts):
        if not part or (part.startswith("<") and part.endswith(">")):
            continue

        for source_term, target_term in ordered_terms:
            part = part.replace(source_term, target_term)
        parts[index] = part

    repaired_text = "".join(parts)
    repaired_text = repaired_text.replace(
        '<LSTag Tooltip="AbilityCheck">Checks</LSTag>',
        '<LSTag Tooltip="AbilityCheck">проверках</LSTag>',
    )
    return repaired_text


def normalize_translation_output(english_text: str, translated_text: str) -> str:
    normalized = normalize_multiline_text(translated_text).strip()

    if "\n" in normalized:
        paragraphs = re.split(r"\n{2,}", normalized)
        normalized = "<br><br>".join(part.replace("\n", "<br>") for part in paragraphs)

    level_match = re.match(r"^Level\s+(\d+):", english_text)
    if level_match:
        expected_prefix = f"Уровень {level_match.group(1)}:"
        prefix_match = re.match(r"^[^:]{1,40}:", normalized)
        if prefix_match:
            normalized = expected_prefix + normalized[prefix_match.end() :]
        elif not normalized.startswith(expected_prefix):
            normalized = f"{expected_prefix} {normalized}".strip()

    return normalized


def assert_translation_quality(
    item_id: str,
    english_text: str,
    translated_text: str,
    relevant_glossary: dict[str, str],
) -> None:
    if normalize_multiline_text(english_text).strip() == normalize_multiline_text(translated_text).strip():
        raise ValueError(f"Translation for id '{item_id}' matches the original English text.")

    visible_text = re.sub(r"<[^>]+>", " ", translated_text)
    for source_term, target_term in relevant_glossary.items():
        if source_term and source_term in visible_text and target_term not in visible_text:
            raise ValueError(
                f"Translation for id '{item_id}' still contains glossary source term '{source_term}'."
            )

    stripped_text = visible_text
    stripped_text = re.sub(r"\[[^\]]+\]", " ", stripped_text)
    suspicious_words = re.findall(r"\b[A-Za-z][A-Za-z'/-]{3,}\b", stripped_text)
    suspicious_words = [
        word for word in suspicious_words if word not in {"LSTag", "Tooltip"} and not word.lower().startswith("h")
    ]
    if suspicious_words:
        raise ValueError(
            f"Translation for id '{item_id}' contains suspicious untranslated words: "
            f"{', '.join(sorted(set(suspicious_words))[:5])}."
        )


def build_jobs(candidates: dict[str, Any], include_existing: bool) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []

    for section_name in ("updates", "adds"):
        section_entries = candidates.get(section_name) or []
        if not isinstance(section_entries, list):
            raise ValueError(f"Candidates field '{section_name}' must be an array.")

        for entry in section_entries:
            if not isinstance(entry, dict):
                raise ValueError(f"Candidates section '{section_name}' contains a non-object entry.")

            content_uid = str(entry.get("contentuid", "")).strip()
            english_text = normalize_multiline_text(entry.get("englishText", ""))
            current_text = normalize_multiline_text(entry.get("text", ""))
            previous_russian_text = normalize_multiline_text(entry.get("russianText", ""))
            old_russian_text = normalize_multiline_text(entry.get("oldRussianText", ""))

            if not content_uid:
                raise ValueError(f"Candidates section '{section_name}' contains empty 'contentuid'.")
            if not english_text.strip():
                raise ValueError(f"Candidates entry '{content_uid}' is missing non-empty 'englishText'.")

            if not include_existing:
                if section_name == "adds" and current_text.strip():
                    continue
                if section_name == "updates" and current_text.strip() and current_text != previous_russian_text:
                    continue

            job: dict[str, Any] = {
                "section": section_name,
                "contentuid": content_uid,
                "englishText": english_text,
            }
            if old_russian_text.strip():
                job["oldRussianText"] = old_russian_text
            jobs.append(job)

    return jobs


def prefill_jobs(
    jobs: list[dict[str, Any]],
    exact_translation_memory: dict[str, str],
    reference_translation_by_uid: dict[str, str],
) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    prefilled_translations: dict[str, str] = {}
    grouped_jobs_by_english: dict[str, list[dict[str, Any]]] = collections.OrderedDict()

    for job in jobs:
        content_uid = job["contentuid"]
        english_text = job["englishText"]

        if content_uid in reference_translation_by_uid:
            prefilled_translations[content_uid] = normalize_translation_output(
                english_text=english_text,
                translated_text=reference_translation_by_uid[content_uid],
            )
            continue

        if english_text in exact_translation_memory:
            prefilled_translations[content_uid] = normalize_translation_output(
                english_text=english_text,
                translated_text=exact_translation_memory[english_text],
            )
            continue

        grouped_jobs_by_english.setdefault(english_text, []).append(job)

    representative_jobs = [job_group[0] for job_group in grouped_jobs_by_english.values()]
    return prefilled_translations, grouped_jobs_by_english, representative_jobs


def build_batches(jobs: list[dict[str, Any]], batch_size: int, max_batch_chars: int) -> list[list[dict[str, Any]]]:
    if batch_size < 1:
        raise ValueError("'batch_size' must be >= 1.")
    if max_batch_chars < 1:
        raise ValueError("'max_batch_chars' must be >= 1.")

    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []
    current_chars = 0

    for job in jobs:
        english_length = len(job["englishText"])
        exceeds_size = len(current_batch) >= batch_size
        exceeds_chars = current_batch and current_chars + english_length > max_batch_chars

        if exceeds_size or exceeds_chars:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0

        current_batch.append(job)
        current_chars += english_length

    if current_batch:
        batches.append(current_batch)

    return batches


def build_user_prompt(
    items: list[dict[str, str]],
    official_glossary: dict[str, str],
    secondary_glossary: dict[str, str],
) -> str:
    items_json = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    glossary_sections: list[str] = []
    if official_glossary:
        glossary_sections.append(f"Official Glossary:\n{build_compact_glossary_text(official_glossary)}")
    if secondary_glossary:
        glossary_sections.append(f"Secondary Glossary:\n{build_compact_glossary_text(secondary_glossary)}")

    glossary_text = "\n\n".join(glossary_sections) if glossary_sections else "Glossary:\n"
    return f"{glossary_text}\n\nInput:\n{items_json}"


def build_compact_glossary_text(glossary: dict[str, str]) -> str:
    lines = [
        f"{source_term} => {target_term}"
        for source_term, target_term in sorted(glossary.items(), key=lambda item: (-len(item[0]), item[0].lower(), item[0]))
    ]
    return "\n".join(lines)


def extract_message_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("OpenRouter response does not contain 'choices'.")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("OpenRouter response does not contain 'message'.")

    content = message.get("content")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        text = "".join(parts).strip()
        if text:
            return text

    raise ValueError("OpenRouter response content is empty or unsupported.")


def parse_translation_response(raw_text: str, expected_ids: list[str]) -> dict[str, str]:
    candidate_text = raw_text.strip()
    if "```" in candidate_text:
        object_start = candidate_text.find("{")
        object_end = candidate_text.rfind("}")
        array_start = candidate_text.find("[")
        array_end = candidate_text.rfind("]")
        if object_start != -1 and object_end != -1 and object_end > object_start:
            candidate_text = candidate_text[object_start : object_end + 1]
        elif array_start != -1 and array_end != -1 and array_end > array_start:
            candidate_text = candidate_text[array_start : array_end + 1]
        else:
            raise ValueError("Model response did not contain valid JSON.")

    data = json.loads(candidate_text)
    if isinstance(data, dict):
        data = data.get("translations")
    if not isinstance(data, list):
        raise ValueError("Model response JSON must be an array or an object with 'translations'.")
    if len(data) != len(expected_ids):
        raise ValueError(
            f"Model response item count mismatch: expected {len(expected_ids)}, got {len(data)}."
        )

    expected_id_set = set(expected_ids)
    result: dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each model response item must be an object.")

        item_id = str(item.get("id", "")).strip()
        item_ru = normalize_multiline_text(item.get("ru", ""))
        if not item_id:
            raise ValueError("Model response item contains empty 'id'.")
        if item_id not in expected_id_set:
            raise ValueError(f"Model response contains unexpected id '{item_id}'.")
        if item_id in result:
            raise ValueError(f"Model response contains duplicate id '{item_id}'.")
        if not item_ru.strip():
            raise ValueError(f"Model response contains empty 'ru' for id '{item_id}'.")
        result[item_id] = item_ru

    missing_ids = [item_id for item_id in expected_ids if item_id not in result]
    if missing_ids:
        raise ValueError(f"Model response is missing ids: {', '.join(missing_ids)}.")
    return result


def extract_usage(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
        }

    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    reasoning_tokens = int(usage.get("reasoning_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens + reasoning_tokens))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
    }


def fetch_model_pricing(model: str, api_key: str) -> dict[str, Decimal]:
    payload = openrouter_request(
        OPENROUTER_MODELS_URL,
        method="GET",
        api_key=api_key,
    )
    models = payload.get("data")
    if not isinstance(models, list):
        raise ValueError("OpenRouter models response does not contain 'data'.")

    for item in models:
        if not isinstance(item, dict):
            continue
        if str(item.get("id", "")).strip() != model:
            continue

        pricing = item.get("pricing")
        if not isinstance(pricing, dict):
            raise ValueError(f"OpenRouter model '{model}' does not contain pricing information.")

        return {
            "prompt": parse_decimal(pricing.get("prompt")),
            "completion": parse_decimal(pricing.get("completion")),
            "request": parse_decimal(pricing.get("request")),
            "internal_reasoning": parse_decimal(pricing.get("internal_reasoning")),
        }

    raise ValueError(f"OpenRouter model '{model}' was not found in /models response.")


def resolve_model_pricing(model: str, api_key: str) -> tuple[dict[str, Decimal], str]:
    if is_free_model(model):
        try:
            pricing = fetch_model_pricing(model, api_key)
            return pricing, "fetched"
        except (error.URLError, RuntimeError, ValueError, json.JSONDecodeError):
            return zero_pricing(), "assumed_free_zero"

    return fetch_model_pricing(model, api_key), "fetched"


def estimate_cost_from_usage(
    usage: dict[str, int],
    pricing: dict[str, Decimal],
) -> Decimal:
    estimated_cost = Decimal("0")
    estimated_cost += Decimal(usage.get("prompt_tokens", 0)) * pricing.get("prompt", Decimal("0"))
    estimated_cost += Decimal(usage.get("completion_tokens", 0)) * pricing.get("completion", Decimal("0"))
    estimated_cost += Decimal(usage.get("reasoning_tokens", 0)) * pricing.get("internal_reasoning", Decimal("0"))
    estimated_cost += pricing.get("request", Decimal("0"))
    return estimated_cost


def fetch_generation_stats(generation_id: str, api_key: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            payload = openrouter_request(
                f"{OPENROUTER_GENERATION_URL}?id={parse.quote(generation_id, safe='')}",
                method="GET",
                api_key=api_key,
            )
            data = payload.get("data")
            if not isinstance(data, dict):
                raise ValueError("OpenRouter generation response does not contain 'data'.")
            return data
        except (error.HTTPError, RuntimeError) as exc:
            last_error = exc
            is_404 = (isinstance(exc, error.HTTPError) and exc.code == 404) or (
                isinstance(exc, RuntimeError) and "HTTP 404" in str(exc)
            )
            if not is_404 or attempt >= 5:
                raise
            time.sleep(min(attempt * 2, 8))
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Failed to fetch generation stats for '{generation_id}'.")


def post_openrouter(
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    use_json_schema: bool,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0,
        "messages": messages,
    }
    if use_json_schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "translation_batch",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["translations"],
                    "properties": {
                        "translations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["id", "ru"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "ru": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        }

    return openrouter_request(
        OPENROUTER_URL,
        method="POST",
        api_key=api_key,
        payload=payload,
    )


def translate_batch(
    batch: list[dict[str, Any]],
    official_glossary: dict[str, str],
    secondary_glossary: dict[str, str],
    effective_glossary: dict[str, str],
    model: str,
    api_key: str,
    retries: int,
    model_pricing: dict[str, Decimal],
    is_free_model_runtime: bool,
) -> tuple[dict[str, str], dict[str, Any]]:
    items: list[dict[str, str]] = []
    for job in batch:
        item: dict[str, str] = {"id": job["contentuid"], "english": job["englishText"]}
        old_ru = job.get("oldRussianText", "").strip()
        if old_ru:
            item["old_ru"] = old_ru
        items.append(item)
    relevant_official_glossary = select_relevant_glossary(official_glossary, [job["englishText"] for job in batch])
    relevant_secondary_glossary = {
        key: value
        for key, value in select_relevant_glossary(secondary_glossary, [job["englishText"] for job in batch]).items()
        if key not in relevant_official_glossary
    }
    user_prompt = build_user_prompt(
        items,
        official_glossary=relevant_official_glossary,
        secondary_glossary=relevant_secondary_glossary,
    )
    expected_ids = [item["id"] for item in items]
    retry_feedback = ""
    use_json_schema = True

    for attempt in range(1, retries + 1):
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            if retry_feedback:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Previous output failed validation.\n"
                            f"Issue: {retry_feedback}\n"
                            "Return a corrected JSON array for the same input. "
                            "Do not leave English words untranslated unless they are preserved tags or placeholders."
                        ),
                    }
                )

            response_payload = post_openrouter(
                model=model,
                api_key=api_key,
                messages=messages,
                use_json_schema=use_json_schema,
            )
            response_text = extract_message_text(response_payload)
            translations = parse_translation_response(response_text, expected_ids)
            usage = extract_usage(response_payload)
            generation_id = str(response_payload.get("id", "")).strip()
            generation_stats: dict[str, Any] = {}
            if generation_id:
                try:
                    generation_stats = fetch_generation_stats(generation_id, api_key)
                except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError, RuntimeError):
                    generation_stats = {}

            for item in items:
                item_id = item["id"]
                relevant_terms = get_relevant_glossary_terms(effective_glossary, item["english"])
                normalized_translation = normalize_translation_output(
                    english_text=item["english"],
                    translated_text=translations[item_id],
                )
                normalized_translation = replace_visible_glossary_terms(
                    translated_text=normalized_translation,
                    relevant_glossary=relevant_terms,
                )
                assert_translation_quality(
                    item_id=item_id,
                    english_text=item["english"],
                    translated_text=normalized_translation,
                    relevant_glossary=relevant_terms,
                )
                translations[item_id] = normalized_translation

            actual_cost = parse_decimal(generation_stats.get("total_cost"))
            native_prompt_tokens = int(generation_stats.get("native_tokens_prompt") or 0)
            native_completion_tokens = int(generation_stats.get("native_tokens_completion") or 0)
            native_reasoning_tokens = int(generation_stats.get("native_tokens_reasoning") or 0)
            estimated_cost = estimate_cost_from_usage(
                usage={
                    "prompt_tokens": native_prompt_tokens or usage["prompt_tokens"],
                    "completion_tokens": native_completion_tokens or usage["completion_tokens"],
                    "reasoning_tokens": native_reasoning_tokens or usage["reasoning_tokens"],
                },
                pricing=model_pricing,
            )

            batch_stats = {
                "generation_id": generation_id,
                "provider_name": str(generation_stats.get("provider_name") or ""),
                "usage": usage,
                "native_prompt_tokens": native_prompt_tokens,
                "native_completion_tokens": native_completion_tokens,
                "native_reasoning_tokens": native_reasoning_tokens,
                "actual_cost_usd": actual_cost,
                "actual_cost_known": "total_cost" in generation_stats,
                "estimated_cost_usd": estimated_cost,
            }
            return translations, batch_stats
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
            retry_feedback = normalize_openrouter_error_message(
                str(exc),
                model=model,
                is_free=is_free_model_runtime,
            )
            if "response content is empty or unsupported" in retry_feedback.lower():
                use_json_schema = False
            if attempt >= retries:
                raise RuntimeError(f"OpenRouter batch failed after {retries} attempts: {retry_feedback}") from exc
            time.sleep(compute_retry_sleep_seconds(attempt, is_free=is_free_model_runtime))

    raise RuntimeError("OpenRouter batch failed unexpectedly.")


def apply_translations(candidates: dict[str, Any], translations: dict[str, str]) -> tuple[int, int]:
    translated_updates = 0
    translated_adds = 0

    for section_name in ("updates", "adds"):
        section_entries = candidates.get(section_name) or []
        for entry in section_entries:
            content_uid = str(entry.get("contentuid", "")).strip()
            if content_uid not in translations:
                continue

            entry["text"] = translations[content_uid]
            if section_name == "updates":
                translated_updates += 1
            else:
                translated_adds += 1

    return translated_updates, translated_adds


def main() -> int:
    args = parse_args()
    load_env_file(Path(".env.local").resolve())

    try:
        model = require_env("OPENROUTER_MODEL")
        api_key = require_env("OPENROUTER_API_KEY")
        free_model = is_free_model(model)

        candidates_path = Path(args.candidates_path).resolve()
        output_path = Path(args.output_path).resolve() if args.output_path.strip() else candidates_path
        usage_report_path = Path(args.usage_report_path).resolve()
        english_path = Path(args.english_path).resolve()
        russian_path = Path(args.russian_path).resolve()
        reference_russian_path = Path(args.reference_russian_path).resolve() if args.reference_russian_path.strip() else None

        candidates = read_json(candidates_path)
        if not isinstance(candidates, dict):
            raise ValueError("Candidates JSON root must be an object.")

        legacy_glossary_path = Path(args.glossary_path).resolve() if args.glossary_path.strip() else None
        official_glossary_path = (
            Path(args.official_glossary_path).resolve() if args.official_glossary_path.strip() else None
        )
        secondary_glossary_path = (
            Path(args.secondary_glossary_path).resolve() if args.secondary_glossary_path.strip() else None
        )

        if legacy_glossary_path is not None:
            official_glossary = read_glossary(legacy_glossary_path)
            secondary_glossary: dict[str, str] = {}
        else:
            if official_glossary_path is None:
                raise ValueError("Official glossary path is required when legacy '--glossary-path' is not used.")
            official_glossary = read_glossary(official_glossary_path)
            secondary_glossary = read_optional_glossary(secondary_glossary_path)

        effective_glossary = merge_glossaries(
            official_glossary=official_glossary,
            secondary_glossary=secondary_glossary,
        )

        jobs = build_jobs(candidates=candidates, include_existing=args.include_existing)
        if not jobs:
            print("[fill-translation-openrouter.py] No translation jobs found. Nothing to do.")
            return 0

        runtime_settings = compute_effective_runtime_settings(
            is_free=free_model,
            batch_size=args.batch_size,
            max_batch_chars=args.max_batch_chars,
            retries=args.retries,
        )
        model_pricing, pricing_resolution = resolve_model_pricing(model, api_key)

        exact_translation_memory: dict[str, str] = {}
        if english_path.exists() and russian_path.exists():
            exact_translation_memory = build_exact_translation_memory(
                english_path=english_path,
                russian_path=russian_path,
            )

        reference_translation_by_uid = (
            build_reference_translation_map(reference_russian_path) if reference_russian_path is not None else {}
        )

        collected_translations, grouped_jobs_by_english, representative_jobs = prefill_jobs(
            jobs=jobs,
            exact_translation_memory=exact_translation_memory,
            reference_translation_by_uid=reference_translation_by_uid,
        )
        prefilled_count = len(collected_translations)
        total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
        }
        total_native_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
        }
        total_actual_cost = Decimal("0")
        total_estimated_cost = Decimal("0")
        actual_cost_available = False
        batch_reports: list[dict[str, Any]] = []

        if representative_jobs:
            batches = build_batches(
                jobs=representative_jobs,
                batch_size=runtime_settings["batch_size"],
                max_batch_chars=runtime_settings["max_batch_chars"],
            )

            for index, batch in enumerate(batches, start=1):
                batch_translations = translate_batch(
                    batch=batch,
                    official_glossary=official_glossary,
                    secondary_glossary=secondary_glossary,
                    effective_glossary=effective_glossary,
                    model=model,
                    api_key=api_key,
                    retries=runtime_settings["retries"],
                    model_pricing=model_pricing,
                    is_free_model_runtime=free_model,
                )
                translated_batch, batch_stats = batch_translations

                for representative_job in batch:
                    representative_uid = representative_job["contentuid"]
                    translated_text = translated_batch[representative_uid]
                    for grouped_job in grouped_jobs_by_english[representative_job["englishText"]]:
                        collected_translations[grouped_job["contentuid"]] = translated_text

                usage = batch_stats["usage"]
                total_usage["prompt_tokens"] += usage["prompt_tokens"]
                total_usage["completion_tokens"] += usage["completion_tokens"]
                total_usage["reasoning_tokens"] += usage["reasoning_tokens"]
                total_usage["total_tokens"] += usage["total_tokens"]
                total_native_usage["prompt_tokens"] += int(batch_stats["native_prompt_tokens"])
                total_native_usage["completion_tokens"] += int(batch_stats["native_completion_tokens"])
                total_native_usage["reasoning_tokens"] += int(batch_stats["native_reasoning_tokens"])
                total_estimated_cost += batch_stats["estimated_cost_usd"]
                if batch_stats["actual_cost_known"]:
                    total_actual_cost += batch_stats["actual_cost_usd"]
                    actual_cost_available = True
                batch_reports.append(
                    {
                        "batchIndex": index,
                        "batchCount": len(batches),
                        "representativeEntries": len(batch),
                        "providerName": batch_stats["provider_name"] or None,
                        "generationId": batch_stats["generation_id"] or None,
                        "usage": {
                            "promptTokens": usage["prompt_tokens"],
                            "completionTokens": usage["completion_tokens"],
                            "reasoningTokens": usage["reasoning_tokens"],
                            "totalTokens": usage["total_tokens"],
                        },
                        "nativeUsage": {
                            "promptTokens": int(batch_stats["native_prompt_tokens"]),
                            "completionTokens": int(batch_stats["native_completion_tokens"]),
                            "reasoningTokens": int(batch_stats["native_reasoning_tokens"]),
                        },
                        "cost": {
                            "estimatedUsd": str(batch_stats["estimated_cost_usd"]),
                            "actualUsd": str(batch_stats["actual_cost_usd"]),
                            "actualKnown": bool(batch_stats["actual_cost_known"]),
                        },
                    }
                )

                print(
                    "[fill-translation-openrouter.py] "
                    f"Mode={'free-aware' if free_model else 'standard'}; "
                    f"Translated batch {index}/{len(batches)}. RepresentativeEntries={len(batch)}; "
                    f"PromptTokens={usage['prompt_tokens']}; CompletionTokens={usage['completion_tokens']}; "
                    f"ReasoningTokens={usage['reasoning_tokens']}; "
                    f"EstimatedCost={format_usd(batch_stats['estimated_cost_usd'])}; "
                    f"ActualCost={format_usd(batch_stats['actual_cost_usd'])}; "
                    f"Provider='{batch_stats['provider_name'] or 'unknown'}'."
                )

        translated_updates, translated_adds = apply_translations(candidates, collected_translations)
        write_json(output_path, candidates)
        if free_model and pricing_resolution == "assumed_free_zero" and actual_cost_available:
            pricing_resolution = "actual_from_generation_only"
        usage_report = {
            "model": model,
            "isFreeModel": free_model,
            "pricingResolution": pricing_resolution,
            "pricing": {
                "promptPerTokenUsd": str(model_pricing["prompt"]),
                "completionPerTokenUsd": str(model_pricing["completion"]),
                "reasoningPerTokenUsd": str(model_pricing["internal_reasoning"]),
                "requestUsd": str(model_pricing["request"]),
                "promptPerMillionUsd": str(model_pricing["prompt"] * Decimal("1000000")),
                "completionPerMillionUsd": str(model_pricing["completion"] * Decimal("1000000")),
                "reasoningPerMillionUsd": str(model_pricing["internal_reasoning"] * Decimal("1000000")),
            },
            "summary": {
                "prefilled": prefilled_count,
                "translatedUpdates": translated_updates,
                "translatedAdds": translated_adds,
                "promptTokens": total_usage["prompt_tokens"],
                "completionTokens": total_usage["completion_tokens"],
                "reasoningTokens": total_usage["reasoning_tokens"],
                "totalTokens": total_usage["total_tokens"],
                "nativePromptTokens": total_native_usage["prompt_tokens"],
                "nativeCompletionTokens": total_native_usage["completion_tokens"],
                "nativeReasoningTokens": total_native_usage["reasoning_tokens"],
                "estimatedCostUsd": str(total_estimated_cost),
                "actualCostUsd": str(total_actual_cost),
                "actualCostKnown": actual_cost_available,
                "mode": "free-aware" if free_model else "standard",
            },
            "runtime": {
                "batchSize": runtime_settings["batch_size"],
                "maxBatchChars": runtime_settings["max_batch_chars"],
                "retries": runtime_settings["retries"],
            },
            "batches": batch_reports,
        }
        write_json(usage_report_path, usage_report)
    except Exception as exc:
        print(normalize_openrouter_error_message(str(exc), model=os.environ.get("OPENROUTER_MODEL", ""), is_free=is_free_model(os.environ.get("OPENROUTER_MODEL", ""))), file=sys.stderr)
        return 1

    print(
        "[fill-translation-openrouter.py] Filled translation candidates successfully. "
        f"Mode={'free-aware' if free_model else 'standard'}; PricingResolution={pricing_resolution}; "
        f"Prefilled={prefilled_count}; Updates={translated_updates}; Adds={translated_adds}; "
        f"Output='{output_path}'; UsageReport='{usage_report_path}'."
    )
    print(
        "[fill-translation-openrouter.py] Usage summary: "
        f"Model='{model}'; PromptTokens={total_usage['prompt_tokens']}; "
        f"CompletionTokens={total_usage['completion_tokens']}; ReasoningTokens={total_usage['reasoning_tokens']}; "
        f"TotalTokens={total_usage['total_tokens']}; NativePromptTokens={total_native_usage['prompt_tokens']}; "
        f"NativeCompletionTokens={total_native_usage['completion_tokens']}; "
        f"NativeReasoningTokens={total_native_usage['reasoning_tokens']}; "
        f"EstimatedCost={format_usd(total_estimated_cost)}; "
        f"ActualCost={format_usd(total_actual_cost) if actual_cost_available else 'n/a'}; "
        f"Mode={'free-aware' if free_model else 'standard'}; "
        f"PricingResolution={pricing_resolution}; "
        f"PricingPerM=prompt:{format_usd(model_pricing['prompt'] * Decimal('1000000'))}, "
        f"completion:{format_usd(model_pricing['completion'] * Decimal('1000000'))}, "
        f"reasoning:{format_usd(model_pricing['internal_reasoning'] * Decimal('1000000'))}, "
        f"request:{format_usd(model_pricing['request'])}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
