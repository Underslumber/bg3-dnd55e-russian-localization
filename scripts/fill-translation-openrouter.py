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
from pathlib import Path
from typing import Any
from urllib import error, request


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_CANDIDATES_PATH = "build/translation-diff/candidates.json"
DEFAULT_GLOSSARY_PATH = "glossary/glossary.normalized.json"
DEFAULT_BATCH_SIZE = 20
DEFAULT_MAX_BATCH_CHARS = 6000
DEFAULT_RETRIES = 3
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
    "- If a glossary term appears, use its glossary translation exactly.\n"
    "- Follow the existing Russian localization style used by this mod.\n"
    "- Translate names, features, classes, and subclass titles as polished in-game UI text, not as literal dictionary glosses.\n"
    '- If the source starts with "Level N:", the result must start with "Уровень N:".\n'
    "- Translate text inside tags too; do not leave words like Checks untranslated.\n"
    "- Do not leave English terms untranslated unless they are placeholders or tag attributes.\n"
    "- Prefer established BG3-style terminology such as спасбросок, атака по возможности, бонус мастерства, владение, очки здоровья.\n"
    "- Preserve placeholders, numbers, variables, XML/HTML tags, LSTag tags, bracketed values like [1], and line breaks.\n"
    "- Keep terminology consistent.\n"
    "- Return only valid JSON.\n\n"
    'Output format:\n[{"id":"...","ru":"..."}]'
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
        default=DEFAULT_GLOSSARY_PATH,
        dest="glossary_path",
        help="Path to glossary JSON dictionary.",
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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_multiline_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


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
    lowered_texts = [text.lower() for text in texts if text]
    if not lowered_texts:
        return {}

    relevant: dict[str, str] = {}
    for source, target in sorted(glossary.items(), key=lambda item: len(item[0]), reverse=True):
        source_lower = source.lower()
        if any(source_lower in text for text in lowered_texts):
            relevant[source] = target
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

            if not content_uid:
                raise ValueError(f"Candidates section '{section_name}' contains empty 'contentuid'.")
            if not english_text.strip():
                raise ValueError(f"Candidates entry '{content_uid}' is missing non-empty 'englishText'.")

            if not include_existing:
                if section_name == "adds" and current_text.strip():
                    continue
                if section_name == "updates" and current_text.strip() and current_text != previous_russian_text:
                    continue

            jobs.append(
                {
                    "section": section_name,
                    "contentuid": content_uid,
                    "englishText": english_text,
                }
            )

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


def build_user_prompt(items: list[dict[str, str]], glossary: dict[str, str]) -> str:
    glossary_json = json.dumps(glossary, ensure_ascii=False, separators=(",", ":"))
    items_json = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return f"Glossary (JSON dictionary):\n{glossary_json}\n\nInput:\n{items_json}"


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
        start = candidate_text.find("[")
        end = candidate_text.rfind("]")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Model response did not contain a JSON array.")
        candidate_text = candidate_text[start : end + 1]

    data = json.loads(candidate_text)
    if not isinstance(data, list):
        raise ValueError("Model response JSON must be an array.")
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
        }

    req = request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def translate_batch(
    batch: list[dict[str, Any]],
    glossary: dict[str, str],
    model: str,
    api_key: str,
    retries: int,
) -> dict[str, str]:
    items = [{"id": job["contentuid"], "english": job["englishText"]} for job in batch]
    relevant_glossary = select_relevant_glossary(glossary, [job["englishText"] for job in batch])
    user_prompt = build_user_prompt(items, relevant_glossary)
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

            for item in items:
                item_id = item["id"]
                relevant_terms = get_relevant_glossary_terms(glossary, item["english"])
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

            return translations
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            retry_feedback = str(exc)
            if "response content is empty or unsupported" in retry_feedback.lower():
                use_json_schema = False
            if attempt >= retries:
                raise RuntimeError(f"OpenRouter batch failed after {retries} attempts: {exc}") from exc
            time.sleep(min(2 * attempt, 6))

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

        candidates_path = Path(args.candidates_path).resolve()
        output_path = Path(args.output_path).resolve() if args.output_path.strip() else candidates_path
        glossary_path = Path(args.glossary_path).resolve()
        english_path = Path(args.english_path).resolve()
        russian_path = Path(args.russian_path).resolve()
        reference_russian_path = Path(args.reference_russian_path).resolve() if args.reference_russian_path.strip() else None

        candidates = read_json(candidates_path)
        glossary = read_json(glossary_path)
        if not isinstance(candidates, dict):
            raise ValueError("Candidates JSON root must be an object.")
        if not isinstance(glossary, dict):
            raise ValueError("Glossary JSON root must be an object.")

        jobs = build_jobs(candidates=candidates, include_existing=args.include_existing)
        if not jobs:
            print("[fill-translation-openrouter.py] No translation jobs found. Nothing to do.")
            return 0

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

        if representative_jobs:
            batches = build_batches(
                jobs=representative_jobs,
                batch_size=args.batch_size,
                max_batch_chars=args.max_batch_chars,
            )

            for index, batch in enumerate(batches, start=1):
                batch_translations = translate_batch(
                    batch=batch,
                    glossary=glossary,
                    model=model,
                    api_key=api_key,
                    retries=args.retries,
                )

                for representative_job in batch:
                    representative_uid = representative_job["contentuid"]
                    translated_text = batch_translations[representative_uid]
                    for grouped_job in grouped_jobs_by_english[representative_job["englishText"]]:
                        collected_translations[grouped_job["contentuid"]] = translated_text

                print(
                    "[fill-translation-openrouter.py] "
                    f"Translated batch {index}/{len(batches)}. RepresentativeEntries={len(batch)}."
                )

        translated_updates, translated_adds = apply_translations(candidates, collected_translations)
        write_json(output_path, candidates)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[fill-translation-openrouter.py] Filled translation candidates successfully. "
        f"Prefilled={prefilled_count}; Updates={translated_updates}; Adds={translated_adds}; Output='{output_path}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
