#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib import error, request


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_GENERATION_URL = "https://openrouter.ai/api/v1/generation"
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
        "-UsageReportPath",
        "--usage-report-path",
        default="build/glossary-review-usage.json",
        dest="usage_report_path",
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


def parse_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def format_usd(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001")))


def openrouter_request(
    url: str,
    *,
    method: str,
    api_key: str,
    payload: Any | None = None,
) -> dict[str, Any]:
    request_data = None
    if payload is not None:
        request_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = request.Request(
        url,
        data=request_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "bg3-dnd55e-russian-localization/1.0",
        },
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


def is_free_model(model: str) -> bool:
    return model.strip().lower().endswith(":free")


def zero_pricing() -> dict[str, Decimal]:
    return {
        "prompt": Decimal("0"),
        "completion": Decimal("0"),
        "request": Decimal("0"),
        "internal_reasoning": Decimal("0"),
    }


def fetch_model_pricing(model: str, api_key: str) -> tuple[dict[str, Decimal], str]:
    if is_free_model(model):
        return zero_pricing(), "assumed_free_zero"

    payload = openrouter_request(
        OPENROUTER_MODELS_URL,
        method="GET",
        api_key=api_key,
    )
    entries = payload.get("data")
    if not isinstance(entries, list):
        return zero_pricing(), "missing_model_catalog"

    model_key = model.strip().lower()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id", "")).strip().lower()
        if entry_id != model_key:
            continue
        pricing = entry.get("pricing")
        if not isinstance(pricing, dict):
            break
        return {
            "prompt": parse_decimal(pricing.get("prompt")),
            "completion": parse_decimal(pricing.get("completion")),
            "request": parse_decimal(pricing.get("request")),
            "internal_reasoning": parse_decimal(pricing.get("internal_reasoning")),
        }, "catalog_match"

    return zero_pricing(), "missing_model_catalog"


def fetch_generation_stats(generation_id: str, api_key: str) -> dict[str, Any]:
    if not generation_id:
        return {}
    payload = openrouter_request(
        f"{OPENROUTER_GENERATION_URL}?id={generation_id}",
        method="GET",
        api_key=api_key,
    )
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return {}


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


def estimate_cost_from_usage(usage: dict[str, int], pricing: dict[str, Decimal]) -> Decimal:
    estimated_cost = Decimal("0")
    estimated_cost += Decimal(usage.get("prompt_tokens", 0)) * pricing.get("prompt", Decimal("0"))
    estimated_cost += Decimal(usage.get("completion_tokens", 0)) * pricing.get("completion", Decimal("0"))
    estimated_cost += Decimal(usage.get("reasoning_tokens", 0)) * pricing.get("internal_reasoning", Decimal("0"))
    estimated_cost += pricing.get("request", Decimal("0"))
    return estimated_cost


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
    model_pricing: dict[str, Decimal],
) -> tuple[dict[str, str], dict[str, Any]]:
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
            usage = extract_usage(response_payload)
            generation_id = str(response_payload.get("id", "")).strip()
            generation_stats = fetch_generation_stats(generation_id, api_key) if generation_id else {}
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
                "usage": usage,
                "generation_id": generation_id,
                "actual_cost_usd": actual_cost,
                "actual_cost_known": "total_cost" in generation_stats,
                "estimated_cost_usd": estimated_cost,
                "native_prompt_tokens": native_prompt_tokens,
                "native_completion_tokens": native_completion_tokens,
                "native_reasoning_tokens": native_reasoning_tokens,
            }
            return translated, batch_stats
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
    model_pricing: dict[str, Decimal],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    try:
        translated, batch_stats = translate_batch(
            batch=batch,
            prompt_text=prompt_text,
            model=model,
            api_key=api_key,
            retries=retries,
            model_pricing=model_pricing,
        )
        return translated, [batch_stats]
    except RuntimeError:
        if len(batch) == 1:
            raise

    midpoint = len(batch) // 2
    left, left_stats = translate_batch_with_fallback(
        batch=batch[:midpoint],
        prompt_text=prompt_text,
        model=model,
        api_key=api_key,
        retries=retries,
        model_pricing=model_pricing,
    )
    right, right_stats = translate_batch_with_fallback(
        batch=batch[midpoint:],
        prompt_text=prompt_text,
        model=model,
        api_key=api_key,
        retries=retries,
        model_pricing=model_pricing,
    )
    merged = dict(left)
    merged.update(right)
    return merged, [*left_stats, *right_stats]


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
        model_pricing, pricing_resolution = fetch_model_pricing(model, api_key)

        input_payload = read_json(Path(args.input_path))
        if not isinstance(input_payload, dict):
            raise ValueError("Input JSON root must be an object.")
        items = input_payload.get("items")
        if not isinstance(items, list):
            raise ValueError("Input JSON must contain 'items' array.")

        prompt_path = Path(args.prompt_path).resolve()
        output_path = Path(args.output_path).resolve()
        usage_report_path = Path(args.usage_report_path).resolve()
        prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        translated_by_uid = load_existing_updates(output_path)
        pending_items = [item for item in items if str(item["contentuid"]) not in translated_by_uid]
        batches = chunked(pending_items, args.batch_size)
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
        translated_entries = 0

        for index, batch in enumerate(batches, start=1):
            batch_translations, batch_stats = translate_batch_with_fallback(
                batch=batch,
                prompt_text=prompt_text,
                model=model,
                api_key=api_key,
                retries=args.retries,
                model_pricing=model_pricing,
            )
            translated_by_uid.update(batch_translations)
            translated_entries += len(batch_translations)
            for stats in batch_stats:
                usage = stats["usage"]
                total_usage["prompt_tokens"] += int(usage["prompt_tokens"])
                total_usage["completion_tokens"] += int(usage["completion_tokens"])
                total_usage["reasoning_tokens"] += int(usage["reasoning_tokens"])
                total_usage["total_tokens"] += int(usage["total_tokens"])
                total_native_usage["prompt_tokens"] += int(stats["native_prompt_tokens"])
                total_native_usage["completion_tokens"] += int(stats["native_completion_tokens"])
                total_native_usage["reasoning_tokens"] += int(stats["native_reasoning_tokens"])
                total_estimated_cost += stats["estimated_cost_usd"]
                if stats["actual_cost_known"]:
                    total_actual_cost += stats["actual_cost_usd"]
                    actual_cost_available = True
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
        write_json(
            usage_report_path,
            {
                "model": model,
                "pricingResolution": pricing_resolution,
                "summary": {
                    "reviewItemCount": len(items),
                    "translatedEntries": translated_entries,
                    "promptTokens": total_usage["prompt_tokens"],
                    "completionTokens": total_usage["completion_tokens"],
                    "reasoningTokens": total_usage["reasoning_tokens"],
                    "totalTokens": total_usage["total_tokens"],
                    "nativePromptTokens": total_native_usage["prompt_tokens"],
                    "nativeCompletionTokens": total_native_usage["completion_tokens"],
                    "nativeReasoningTokens": total_native_usage["reasoning_tokens"],
                    "estimatedCostUsd": format_usd(total_estimated_cost),
                    "actualCostUsd": format_usd(total_actual_cost),
                    "actualCostKnown": actual_cost_available,
                },
            },
        )
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[review-glossary-openrouter.py] "
        f"Prepared {len(translated_by_uid)} point fixes in '{output_path}'. "
        f"UsageReport='{usage_report_path}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
