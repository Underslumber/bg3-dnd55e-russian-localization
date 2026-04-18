#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib import error, request


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 120
PLACEHOLDER_PATTERN = re.compile(
    r"%\d+\$[sd]|%[sd]|\[\d+\]|&lt;br&gt;|<LSTag[^>]*>|</LSTag>|\{[^}]+\}",
    re.IGNORECASE,
)
RUSSIAN_WORD_PATTERN = re.compile(r"[А-Яа-яЁё]+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send glossary review items to OpenRouter and save point translation fixes."
    )
    parser.add_argument(
        "-InputPath",
        "--input-path",
        default="build/glossary-review-input.json",
        dest="input_path",
    )
    parser.add_argument(
        "-PromptPath",
        "--prompt-path",
        default="docs/official-localization/prompt-glossary-review.md",
        dest="prompt_path",
    )
    parser.add_argument(
        "-OutputPath",
        "--output-path",
        default="build/glossary-review-fixes.json",
        dest="output_path",
    )
    parser.add_argument(
        "-BatchSize",
        "--batch-size",
        type=int,
        default=20,
        dest="batch_size",
    )
    parser.add_argument(
        "-Retries",
        "--retries",
        type=int,
        default=3,
        dest="retries",
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
        if key and key not in os.environ:
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


def load_existing_updates(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    payload = read_json(path)
    if not isinstance(payload, dict):
        return {}
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return {}

    loaded: dict[str, str] = {}
    for item in updates:
        if not isinstance(item, dict):
            continue
        content_uid = str(item.get("contentuid", "")).strip()
        text = str(item.get("text", ""))
        if content_uid:
            loaded[content_uid] = text
    return loaded


def get_placeholder_tokens(text: str) -> list[str]:
    tokens = PLACEHOLDER_PATTERN.findall(str(text or ""))
    normalized: list[str] = []
    for token in tokens:
        token_lower = token.lower()
        if token_lower.startswith("<lstag"):
            normalized.append("<LSTag>")
        elif token_lower == "</lstag>":
            normalized.append("</LSTag>")
        elif token_lower == "&lt;br&gt;":
            normalized.append("<br>")
        else:
            normalized.append(token)
    return normalized


def get_placeholder_signature(text: str) -> dict[str, object]:
    tokens = get_placeholder_tokens(text)
    exact_tokens = [token for token in tokens if token not in {"<LSTag>", "</LSTag>"}]
    return {
        "exact": Counter(exact_tokens),
        "open_lstag": sum(1 for token in tokens if token == "<LSTag>"),
        "close_lstag": sum(1 for token in tokens if token == "</LSTag>"),
    }


def contains_glossary_term_loosely(visible_text: str, glossary_term: str) -> bool:
    if glossary_term.casefold() in visible_text.casefold():
        return True

    text_words = RUSSIAN_WORD_PATTERN.findall(visible_text.casefold())
    term_words = RUSSIAN_WORD_PATTERN.findall(glossary_term.casefold())
    if not term_words:
        return False

    for term_word in term_words:
        if len(term_word) <= 2:
            if term_word not in text_words:
                return False
            continue

        if len(term_word) <= 5:
            stem_length = 2
        else:
            stem_length = 4
        stem = term_word[:stem_length]
        if not any(word.startswith(stem) for word in text_words):
            return False

    return True


def post_openrouter(model: str, api_key: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "glossary_review_batch",
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
                                "required": ["contentuid", "text"],
                                "properties": {
                                    "contentuid": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                            },
                        }
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
            "User-Agent": "bg3-dnd55e-russian-localization/1.0",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_message_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("OpenRouter response does not contain 'choices'.")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("OpenRouter response choice does not contain 'message'.")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        return "".join(parts)
    raise ValueError("OpenRouter response content is empty or unsupported.")


def parse_translation_response(response_text: str, expected_ids: list[str]) -> dict[str, str]:
    payload = json.loads(response_text)
    if not isinstance(payload, dict):
        raise ValueError("LLM response root must be an object.")
    translations = payload.get("translations")
    if not isinstance(translations, list):
        raise ValueError("LLM response must contain 'translations' array.")

    parsed: dict[str, str] = {}
    for item in translations:
        if not isinstance(item, dict):
            raise ValueError("Each translation item must be an object.")
        content_uid = str(item.get("contentuid", "")).strip()
        text = str(item.get("text", ""))
        if not content_uid:
            raise ValueError("Each translation item must contain non-empty 'contentuid'.")
        if content_uid in parsed:
            raise ValueError(f"Duplicate contentuid in LLM response: '{content_uid}'.")
        parsed[content_uid] = text

    if sorted(parsed) != sorted(expected_ids):
        raise ValueError("LLM response contentuid set does not match requested batch.")
    return parsed


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if size <= 0:
        raise ValueError("BatchSize must be greater than 0.")
    return [items[index : index + size] for index in range(0, len(items), size)]


def build_user_prompt(batch: list[dict[str, Any]]) -> str:
    compact_items = [
        {
            "contentuid": item["contentuid"],
            "english_text": item["english_text"],
            "current_russian_text": item["current_russian_text"],
            "required_glossary_terms": item["required_glossary_terms"],
        }
        for item in batch
    ]
    return json.dumps({"items": compact_items}, ensure_ascii=False, indent=2)


def assert_translation_quality(item: dict[str, Any], translated_text: str) -> None:
    expected_signature = get_placeholder_signature(item["english_text"])
    translated_signature = get_placeholder_signature(translated_text)
    if expected_signature != translated_signature:
        raise ValueError(
            f"Translation for '{item['contentuid']}' changed placeholders or tags."
        )

    visible_text = re.sub(r"<[^>]+>", " ", translated_text)
    for term in item["required_glossary_terms"]:
        russian_term = str(term["russian"])
        if not contains_glossary_term_loosely(visible_text, russian_term):
            raise ValueError(
                f"Translation for '{item['contentuid']}' does not contain glossary term '{russian_term}'."
            )


def translate_batch(
    *,
    batch: list[dict[str, Any]],
    prompt_text: str,
    model: str,
    api_key: str,
    retries: int,
) -> dict[str, str]:
    expected_ids = [str(item["contentuid"]) for item in batch]
    feedback = ""
    debug_path = Path("build/glossary-review-debug.json").resolve()

    for attempt in range(1, retries + 1):
        try:
            messages = [
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": build_user_prompt(batch)},
            ]
            if feedback:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Previous output failed validation.\n"
                            f"Issue: {feedback}\n"
                            "Return corrected JSON for the same batch."
                        ),
                    }
                )
            response_payload = post_openrouter(model=model, api_key=api_key, messages=messages)
            response_text = extract_message_text(response_payload)
            translated = parse_translation_response(response_text, expected_ids)
            for item in batch:
                try:
                    assert_translation_quality(item, translated[item["contentuid"]])
                except ValueError as exc:
                    write_json(
                        debug_path,
                        {
                            "attempt": attempt,
                            "contentuid": item["contentuid"],
                            "error": str(exc),
                            "english_text": item["english_text"],
                            "current_russian_text": item["current_russian_text"],
                            "translated_text": translated[item["contentuid"]],
                            "required_glossary_terms": item["required_glossary_terms"],
                            "english_signature": get_placeholder_signature(item["english_text"]),
                            "translated_signature": get_placeholder_signature(translated[item["contentuid"]]),
                        },
                    )
                    raise
            return translated
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            feedback = str(exc)
            if attempt >= retries:
                raise RuntimeError(f"OpenRouter batch failed after {retries} attempts: {exc}") from exc
            time.sleep(min(attempt * 2, 6))

    raise RuntimeError("OpenRouter batch failed unexpectedly.")


def translate_batch_with_fallback(
    *,
    batch: list[dict[str, Any]],
    prompt_text: str,
    model: str,
    api_key: str,
    retries: int,
) -> dict[str, str]:
    try:
        return translate_batch(
            batch=batch,
            prompt_text=prompt_text,
            model=model,
            api_key=api_key,
            retries=retries,
        )
    except RuntimeError:
        if len(batch) == 1:
            raise

    midpoint = len(batch) // 2
    left = translate_batch_with_fallback(
        batch=batch[:midpoint],
        prompt_text=prompt_text,
        model=model,
        api_key=api_key,
        retries=retries,
    )
    right = translate_batch_with_fallback(
        batch=batch[midpoint:],
        prompt_text=prompt_text,
        model=model,
        api_key=api_key,
        retries=retries,
    )
    merged = dict(left)
    merged.update(right)
    return merged


def write_progress_output(
    *,
    output_path: Path,
    input_path: Path,
    prompt_path: Path,
    items: list[dict[str, Any]],
    translated_by_uid: dict[str, str],
) -> None:
    updates = []
    for item in items:
        content_uid = str(item["contentuid"])
        text = translated_by_uid.get(content_uid)
        if text is None:
            continue
        updates.append(
            {
                "contentuid": content_uid,
                "text": text,
                "englishText": item["english_text"],
                "russianText": item["current_russian_text"],
                "requiredGlossaryTerms": item["required_glossary_terms"],
            }
        )

    write_json(
        output_path,
        {
            "sourceInputPath": str(input_path.resolve()),
            "promptPath": str(prompt_path.resolve()),
            "updates": updates,
            "adds": [],
        },
    )


def main() -> int:
    args = parse_args()
    load_env_file(Path(".env.local").resolve())

    try:
        model = require_env("OPENROUTER_MODEL")
        api_key = require_env("OPENROUTER_API_KEY")

        input_payload = read_json(Path(args.input_path))
        if not isinstance(input_payload, dict):
            raise ValueError("Input JSON root must be an object.")
        items = input_payload.get("items")
        if not isinstance(items, list):
            raise ValueError("Input JSON must contain 'items' array.")

        prompt_path = Path(args.prompt_path).resolve()
        output_path = Path(args.output_path).resolve()
        prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        translated_by_uid = load_existing_updates(output_path)
        pending_items = [item for item in items if str(item["contentuid"]) not in translated_by_uid]
        batches = chunked(pending_items, args.batch_size)

        for index, batch in enumerate(batches, start=1):
            translated_by_uid.update(
                translate_batch_with_fallback(
                    batch=batch,
                    prompt_text=prompt_text,
                    model=model,
                    api_key=api_key,
                    retries=args.retries,
                )
            )
            write_progress_output(
                output_path=output_path,
                input_path=Path(args.input_path),
                prompt_path=prompt_path,
                items=items,
                translated_by_uid=translated_by_uid,
            )
            print(
                "[review-glossary-openrouter.py] "
                f"Translated batch {index}/{len(batches)}. Entries={len(batch)}; "
                f"Saved={len(translated_by_uid)}/{len(items)}."
            )
        write_progress_output(
            output_path=output_path,
            input_path=Path(args.input_path),
            prompt_path=prompt_path,
            items=items,
            translated_by_uid=translated_by_uid,
        )
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[review-glossary-openrouter.py] "
        f"Prepared {len(translated_by_uid)} point fixes in '{output_path}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
