#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
import xml.etree.ElementTree as ET
from typing import Any

USD_RUB_RATE_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
USD_MARKUP_MULTIPLIER = Decimal("1.2")
RUB_PRECISION = Decimal("0.0001")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a Russian GitHub Step Summary for the autopilot workflow.")
    parser.add_argument("-RunReportPath", "--run-report-path", required=True, dest="run_report_path")
    parser.add_argument("-OutputPath", "--output-path", required=True, dest="output_path")
    parser.add_argument("-RunUrl", "--run-url", default="", dest="run_url")
    parser.add_argument("-CommitCreated", "--commit-created", default="false", dest="commit_created")
    parser.add_argument("-TagCreated", "--tag-created", default="false", dest="tag_created")
    parser.add_argument("-TagName", "--tag-name", default="", dest="tag_name")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: '{path}'.")
    return payload


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def parse_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_decimal_max(value: Decimal, precision: Decimal) -> str:
    return format_decimal(value.quantize(precision, rounding=ROUND_HALF_UP))


def fetch_usd_rub_market_rate() -> Decimal | None:
    try:
        with urlopen(USD_RUB_RATE_URL, timeout=10) as response:
            payload = response.read()
    except (URLError, TimeoutError, OSError):
        return None

    root = ET.fromstring(payload)
    for valute in root.findall("Valute"):
        char_code = (valute.findtext("CharCode") or "").strip()
        if char_code != "USD":
            continue

        nominal_text = (valute.findtext("Nominal") or "1").strip()
        value_text = (valute.findtext("Value") or "0").strip().replace(",", ".")
        nominal = parse_decimal(nominal_text)
        value = parse_decimal(value_text)
        if nominal == 0:
            return None
        return value / nominal

    return None


def format_cost(usage: dict[str, Any]) -> str:
    usd_cost = Decimal("0")
    if bool(usage.get("actualCostKnown")):
        usd_cost = parse_decimal(usage.get("actualCostUsd"))
    elif bool(usage.get("available")):
        usd_cost = parse_decimal(usage.get("estimatedCostUsd"))

    usd_part = f"${format_decimal(usd_cost)}🇺🇸"
    market_rate = fetch_usd_rub_market_rate()
    if market_rate is None:
        return usd_part

    rub_cost = (usd_cost * market_rate * USD_MARKUP_MULTIPLIER).quantize(RUB_PRECISION, rounding=ROUND_HALF_UP)
    return f"{usd_part}| ₽{format_decimal_max(rub_cost, RUB_PRECISION)}🇷🇺"


def main() -> int:
    args = parse_args()
    run_report_path = Path(args.run_report_path).resolve()
    output_path = Path(args.output_path).resolve()
    report = load_json(run_report_path)

    mode = report.get("mode") if isinstance(report.get("mode"), dict) else {}
    trigger = report.get("trigger") if isinstance(report.get("trigger"), dict) else {}
    upstream = report.get("upstream") if isinstance(report.get("upstream"), dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    usage = report.get("usage") if isinstance(report.get("usage"), dict) else {}
    actions = report.get("actions") if isinstance(report.get("actions"), dict) else {}
    error = report.get("error") if isinstance(report.get("error"), dict) else {}

    run_url = args.run_url.strip() or (
        f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    )
    commit_created = as_bool(args.commit_created)
    tag_created = as_bool(args.tag_created)
    tag_name = args.tag_name.strip() or str(actions.get("tagName") or "")
    override_used = str(mode.get("override") or "inherit") != "inherit"
    reason = str(report.get("reason") or "")
    error_message = str(error.get("message") or "")

    lines = [
        "# Автопилот синхронизации перевода",
        "",
        f"- Итоговый статус: `{report.get('status', 'unknown')}`",
        f"- Режим работы: `{mode.get('effective', 'off')}`",
        f"- Override использован: `{'да' if override_used else 'нет'}`",
        f"- Источник режима: `{mode.get('source', 'unknown')}`",
        f"- Событие запуска: `{trigger.get('event', '') or 'unknown'}`",
        f"- Причина ручного запуска: `{trigger.get('reason', '') or 'не указана'}`",
        f"- Старый hash upstream: `{upstream.get('previousProcessedSha256', '') or 'не задан'}`",
        f"- Новый hash upstream: `{upstream.get('currentSha256', '') or 'не определён'}`",
        f"- Изменения upstream обнаружены: `{'да' if upstream.get('changed') else 'нет'}`",
        f"- Принудительная проверка: `{'да' if trigger.get('forceCheck') else 'нет'}`",
        f"- Принудительный релиз: `{'да' if trigger.get('forceRelease') else 'нет'}`",
        "",
        "## Статистика",
        "",
        f"- Missing in Russian: `{summary.get('missingInRussianCount', 0)}`",
        f"- Version mismatches: `{summary.get('versionMismatchCount', 0)}`",
        f"- Stale only in Russian: `{summary.get('staleOnlyInRussianCount', 0)}`",
        f"- Переведено записей: `{usage.get('translatedTotal', 0)}`",
        f"- Потрачено: `{format_cost(usage)}`",
        "",
        "## Действия",
        "",
        f"- Коммит создан: `{'да' if commit_created else 'нет'}`",
        f"- Тег создан: `{'да' if tag_created else 'нет'}`",
        f"- Имя тега: `{tag_name or 'не создавался'}`",
        f"- Релиз инициирован: `{'да' if tag_created else 'нет'}`",
        f"- Примечание: релиз и prerelease создаются только в режиме `full`",
        "",
        "## Отчёты",
        "",
        f"- [Run report]({run_url})",
        f"- Артефакты: доступны в этом запуске workflow",
    ]

    if reason:
        lines.extend(["", f"- Причина завершения: {reason}"])

    if error_message:
        lines.extend(["", f"- Причина ошибки: {error_message}"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[write-autopilot-summary.py] Summary written to '{output_path}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
