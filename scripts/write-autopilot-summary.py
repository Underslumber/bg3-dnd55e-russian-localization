#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


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


def format_cost(usage: dict[str, Any]) -> str:
    if bool(usage.get("actualCostKnown")):
        return f"${usage.get('actualCostUsd') or '0'}"
    if bool(usage.get("available")):
        return f"${usage.get('estimatedCostUsd') or '0'}"
    return "$0"


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
