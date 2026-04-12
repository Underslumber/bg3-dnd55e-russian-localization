#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
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
        help="Maximum number of strings per API request.",
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


def build_jobs(
    candidates: dict[str, Any],
    include_existing: bool,
) -> list[dict[str, Any]]:
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


def post_openrouter(model: str, api_key: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
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

    for attempt in range(1, retries + 1):
        try:
            response_payload = post_openrouter(model=model, api_key=api_key, system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)
            response_text = extract_message_text(response_payload)
            return parse_translation_response(response_text, expected_ids)
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            if attempt >= retries:
                raise RuntimeError(
                    f"OpenRouter batch failed after {retries} attempts: {exc}"
                ) from exc
            time.sleep(min(2 * attempt, 6))

    raise RuntimeError("OpenRouter batch failed unexpectedly.")


def apply_translations(candidates: dict[str, Any], translations: dict[str, str]) -> tuple[int, int]:
    translated_updates = 0
    translated_adds = 0

    for section_name in ("updates", "adds"):
        section_entries = candidates.get(section_name) or []
        for entry in section_entries:
            content_uid = str(entry.get("contentuid", "")).strip()
            if content_uid in translations:
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

        batches = build_batches(jobs=jobs, batch_size=args.batch_size, max_batch_chars=args.max_batch_chars)
        collected_translations: dict[str, str] = {}

        for index, batch in enumerate(batches, start=1):
            batch_translations = translate_batch(
                batch=batch,
                glossary=glossary,
                model=model,
                api_key=api_key,
                retries=args.retries,
            )
            collected_translations.update(batch_translations)
            print(
                "[fill-translation-openrouter.py] "
                f"Translated batch {index}/{len(batches)}. Entries={len(batch)}."
            )

        translated_updates, translated_adds = apply_translations(candidates, collected_translations)
        write_json(output_path, candidates)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[fill-translation-openrouter.py] Filled translation candidates successfully. "
        f"Updates={translated_updates}; Adds={translated_adds}; Output='{output_path}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
