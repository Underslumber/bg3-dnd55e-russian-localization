#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_MODES = {"off", "sync_only", "full"}
VALID_RELEASE_CHANNELS = {"stable", "prerelease"}
DEFAULT_UPSTREAM_ENGLISH_URL = (
    "https://raw.githubusercontent.com/Yoonmoonsik/dnd55e/main/"
    "Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the autopilot translation synchronization workflow.")
    parser.add_argument("-Mode", "--mode", required=True, dest="mode")
    parser.add_argument("-ModeSource", "--mode-source", default="variable", dest="mode_source")
    parser.add_argument("-ModeOverride", "--mode-override", default="inherit", dest="mode_override")
    parser.add_argument("-Trigger", "--trigger", default="", dest="trigger")
    parser.add_argument("-Reason", "--reason", default="", dest="reason")
    parser.add_argument("-ForceCheck", "--force-check", action="store_true", dest="force_check")
    parser.add_argument("-ForceRelease", "--force-release", action="store_true", dest="force_release")
    parser.add_argument("-IncludeExisting", "--include-existing", action="store_true", dest="include_existing")
    parser.add_argument(
        "-ReleaseChannel",
        "--release-channel",
        default="stable",
        dest="release_channel",
    )
    parser.add_argument("-CustomTag", "--custom-tag", default="", dest="custom_tag")
    parser.add_argument(
        "-StatePath",
        "--state-path",
        default=".github/autopilot/state.json",
        dest="state_path",
    )
    parser.add_argument(
        "-UpstreamCheckPath",
        "--upstream-check-path",
        default="build/autopilot/upstream-check.json",
        dest="upstream_check_path",
    )
    parser.add_argument(
        "-RunReportPath",
        "--run-report-path",
        default="build/autopilot/run-report.json",
        dest="run_report_path",
    )
    parser.add_argument(
        "-CommitMessagePath",
        "--commit-message-path",
        default="build/autopilot/commit-message.txt",
        dest="commit_message_path",
    )
    parser.add_argument(
        "-ResolvedTagPath",
        "--resolved-tag-path",
        default="build/autopilot/resolved-tag.json",
        dest="resolved_tag_path",
    )
    parser.add_argument(
        "-RepositoryPath",
        "--repository-path",
        default=".",
        dest="repository_path",
    )
    parser.add_argument(
        "-RussianPath",
        "--russian-path",
        default="Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
        dest="russian_path",
    )
    parser.add_argument(
        "-OutputDir",
        "--output-dir",
        default="build/translation-diff",
        dest="output_dir",
    )
    parser.add_argument(
        "-EnglishPath",
        "--english-path",
        default=".cache/upstream/english.xml",
        dest="english_path",
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
        default="glossary/glossary.official.json",
        dest="official_glossary_path",
        help="Path to the primary official glossary JSON dictionary.",
    )
    parser.add_argument(
        "-SecondaryGlossaryPath",
        "--secondary-glossary-path",
        default="glossary/glossary.normalized.json",
        dest="secondary_glossary_path",
        help="Path to the secondary fallback glossary JSON dictionary.",
    )
    parser.add_argument(
        "-UpstreamEnglishUrl",
        "--upstream-english-url",
        default=DEFAULT_UPSTREAM_ENGLISH_URL,
        dest="upstream_english_url",
    )
    parser.add_argument(
        "-TrustedRegistryPath",
        "--trusted-registry-path",
        default="glossary/trusted-contentuid-versions.json",
        dest="trusted_registry_path",
    )
    return parser.parse_args()


def get_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: '{path}'.")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_state_shape(payload: dict[str, Any] | None) -> dict[str, Any]:
    current = payload if isinstance(payload, dict) else {}
    upstream = current.get("upstream") if isinstance(current.get("upstream"), dict) else {}
    release = current.get("release") if isinstance(current.get("release"), dict) else {}
    return {
        "upstream": {
            "english_xml_url": str(upstream.get("english_xml_url") or ""),
            "last_processed_sha256": str(upstream.get("last_processed_sha256") or ""),
            "last_processed_commit_sha": str(upstream.get("last_processed_commit_sha") or ""),
            "last_processed_at": str(upstream.get("last_processed_at") or ""),
            "last_seen_etag": str(upstream.get("last_seen_etag") or ""),
            "last_seen_last_modified": str(upstream.get("last_seen_last_modified") or ""),
        },
        "release": {
            "last_tag": str(release.get("last_tag") or ""),
            "last_release_commit": str(release.get("last_release_commit") or ""),
        },
    }


def run_command(args: list[str], repository_path: Path, description: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=repository_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        details: list[str] = [f"{description} завершилось с кодом {result.returncode}."]
        stdout_text = (result.stdout or "").strip()
        stderr_text = (result.stderr or "").strip()
        if stderr_text:
            details.append(f"stderr: {stderr_text}")
        elif stdout_text:
            details.append(f"stdout: {stdout_text}")
        raise RuntimeError(" ".join(details))
    return result


def git_output(repository_path: Path, *git_args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository_path), *git_args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "Git command failed.")
    return result.stdout.strip()


def git_changed_files(repository_path: Path) -> list[str]:
    output = git_output(repository_path, "status", "--short")
    changed_files: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        changed_files.append(line[3:].strip())
    return changed_files


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json(path)


def read_summary(output_dir: Path) -> dict[str, Any]:
    summary_path = output_dir / "summary.json"
    summary = load_optional_json(summary_path)
    if summary is None:
        return {
            "path": str(summary_path),
            "missingInRussianCount": 0,
            "versionMismatchCount": 0,
            "staleOnlyInRussianCount": 0,
        }
    return {
        "path": str(summary_path),
        "missingInRussianCount": int(summary.get("missingInRussianCount") or 0),
        "versionMismatchCount": int(summary.get("versionMismatchCount") or 0),
        "staleOnlyInRussianCount": int(summary.get("staleOnlyInRussianCount") or 0),
    }


def read_usage(output_dir: Path) -> dict[str, Any]:
    usage_path = output_dir / "openrouter-usage.json"
    usage = load_optional_json(usage_path)
    if usage is None:
        return {
            "path": str(usage_path),
            "translatedUpdates": 0,
            "translatedAdds": 0,
            "translatedTotal": 0,
            "prefilled": 0,
            "estimatedCostUsd": "0",
            "actualCostUsd": "0",
            "actualCostKnown": False,
            "available": False,
        }

    usage_summary = usage.get("summary") if isinstance(usage.get("summary"), dict) else {}
    translated_updates = int(usage_summary.get("translatedUpdates") or 0)
    translated_adds = int(usage_summary.get("translatedAdds") or 0)
    return {
        "path": str(usage_path),
        "translatedUpdates": translated_updates,
        "translatedAdds": translated_adds,
        "translatedTotal": translated_updates + translated_adds,
        "prefilled": int(usage_summary.get("prefilled") or 0),
        "estimatedCostUsd": str(usage_summary.get("estimatedCostUsd") or "0"),
        "actualCostUsd": str(usage_summary.get("actualCostUsd") or "0"),
        "actualCostKnown": bool(usage_summary.get("actualCostKnown")),
        "available": True,
    }


def build_commit_message(
    *,
    changed_files: list[str],
    upstream_sha256: str,
    mode: str,
    summary: dict[str, Any],
    usage: dict[str, Any],
) -> str:
    if changed_files == [".github/autopilot/state.json"]:
        title = "Обновление состояния автопилота"
    else:
        title = "Обновление перевода из upstream dnd55e"

    lines = [
        title,
        "",
        f"Upstream-SHA256: {upstream_sha256}",
        f"Missing: {summary['missingInRussianCount']}",
        f"VersionMismatch: {summary['versionMismatchCount']}",
        f"StaleOnlyInRussian: {summary['staleOnlyInRussianCount']}",
        f"Translated: {usage['translatedTotal']}",
        f"Mode: {mode}",
    ]
    return "\n".join(lines) + "\n"


def resolve_release_channel(value: str) -> str:
    normalized = value.strip().lower() or "stable"
    if normalized not in VALID_RELEASE_CHANNELS:
        return "stable"
    return normalized


def main() -> int:
    args = parse_args()
    repository_path = Path(args.repository_path).resolve()
    state_path = Path(args.state_path).resolve()
    upstream_check_path = Path(args.upstream_check_path).resolve()
    run_report_path = Path(args.run_report_path).resolve()
    commit_message_path = Path(args.commit_message_path).resolve()
    resolved_tag_path = Path(args.resolved_tag_path).resolve()
    output_dir = Path(args.output_dir).resolve()
    russian_path = Path(args.russian_path).resolve()
    english_path = Path(args.english_path).resolve()
    glossary_path = Path(args.glossary_path).resolve() if args.glossary_path.strip() else None
    official_glossary_path = Path(args.official_glossary_path).resolve() if args.official_glossary_path.strip() else None
    secondary_glossary_path = (
        Path(args.secondary_glossary_path).resolve() if args.secondary_glossary_path.strip() else None
    )
    trusted_registry_path = Path(args.trusted_registry_path).resolve() if args.trusted_registry_path.strip() else None
    scripts_dir = Path(__file__).resolve().parent

    report: dict[str, Any] = {
        "generatedAt": get_now_iso(),
        "status": "error",
        "reason": "",
        "mode": {
            "effective": args.mode,
            "source": args.mode_source,
            "override": args.mode_override,
        },
        "trigger": {
            "event": args.trigger or os.environ.get("GITHUB_EVENT_NAME", ""),
            "reason": args.reason.strip(),
            "forceCheck": bool(args.force_check),
            "forceRelease": bool(args.force_release),
            "includeExisting": bool(args.include_existing),
        },
        "upstream": {},
        "summary": {
            "missingInRussianCount": 0,
            "versionMismatchCount": 0,
            "staleOnlyInRussianCount": 0,
        },
        "usage": {
            "translatedUpdates": 0,
            "translatedAdds": 0,
            "translatedTotal": 0,
            "estimatedCostUsd": "0",
            "actualCostUsd": "0",
            "actualCostKnown": False,
            "available": False,
        },
        "paths": {
            "state": str(state_path),
            "upstreamCheck": str(upstream_check_path),
            "runReport": str(run_report_path),
            "commitMessage": str(commit_message_path),
            "resolvedTag": str(resolved_tag_path),
            "outputDir": str(output_dir),
            "russianXml": str(russian_path),
            "englishXml": str(english_path),
            "officialGlossary": str(official_glossary_path) if official_glossary_path is not None else "",
            "secondaryGlossary": str(secondary_glossary_path) if secondary_glossary_path is not None else "",
            "trustedRegistry": str(trusted_registry_path) if trusted_registry_path is not None else "",
        },
        "actions": {
            "processRequested": False,
            "updateAttempted": False,
            "validationAttempted": False,
            "stateUpdated": False,
            "commitRequired": False,
            "tagRequired": False,
            "releaseTriggered": False,
            "tagName": "",
        },
        "git": {
            "branch": "",
            "headSha": "",
            "changedFiles": [],
        },
        "error": None,
    }

    try:
        if args.mode not in VALID_MODES:
            raise ValueError(f"Неподдерживаемый режим автопилота: '{args.mode}'.")

        branch_name = git_output(repository_path, "branch", "--show-current")
        head_sha = git_output(repository_path, "rev-parse", "HEAD")
        report["git"]["branch"] = branch_name
        report["git"]["headSha"] = head_sha

        state = ensure_state_shape(load_optional_json(state_path))
        upstream_check = load_json(upstream_check_path)
        report["upstream"] = {
            "englishXmlUrl": str(upstream_check.get("upstreamEnglishXmlUrl") or args.upstream_english_url),
            "previousProcessedSha256": str(upstream_check.get("previousProcessedSha256") or ""),
            "currentSha256": str(upstream_check.get("currentSha256") or ""),
            "changed": bool(upstream_check.get("changed")),
            "etag": str(upstream_check.get("etag") or ""),
            "lastModified": str(upstream_check.get("lastModified") or ""),
            "forceCheckApplied": bool(args.force_check),
        }

        should_process = args.mode != "off" and (
            bool(upstream_check.get("changed")) or args.force_check or args.force_release
        )
        report["actions"]["processRequested"] = should_process

        if args.mode == "off":
            report["status"] = "skipped"
            report["reason"] = "Автопилот отключён."
            write_json(run_report_path, report)
            print("[run-autopilot.py] Автопилот отключён. Завершение без изменений.")
            return 0

        if not should_process:
            report["status"] = "skipped"
            report["reason"] = "Изменения в upstream не обнаружены."
            write_json(run_report_path, report)
            print("[run-autopilot.py] Изменения в upstream не обнаружены. Обновление не требуется.")
            return 0

        update_args = [
            sys.executable,
            str(scripts_dir / "update-translation-openrouter.py"),
            "--russian-path",
            str(russian_path),
            "--english-path",
            str(english_path),
            "--output-dir",
            str(output_dir),
        ]
        if glossary_path is not None:
            update_args.extend(["--glossary-path", str(glossary_path)])
        else:
            if official_glossary_path is not None:
                update_args.extend(["--official-glossary-path", str(official_glossary_path)])
            if secondary_glossary_path is not None:
                update_args.extend(["--secondary-glossary-path", str(secondary_glossary_path)])
        if trusted_registry_path is not None:
            update_args.extend(["--trusted-registry-path", str(trusted_registry_path)])
        if args.include_existing:
            update_args.append("--include-existing")

        report["actions"]["updateAttempted"] = True
        run_command(update_args, repository_path, "Обновление перевода")

        validate_args = [
            sys.executable,
            str(scripts_dir / "validate-translation-xml.py"),
            "--xml-path",
            str(russian_path),
        ]
        report["actions"]["validationAttempted"] = True
        run_command(validate_args, repository_path, "Проверка XML")

        report["summary"] = read_summary(output_dir)
        report["usage"] = read_usage(output_dir)

        resolved_tag = ""
        if args.mode == "full":
            release_channel = resolve_release_channel(args.release_channel)
            resolve_args = [
                sys.executable,
                str(scripts_dir / "resolve-release-tag.py"),
                "--repository-path",
                str(repository_path),
                "--release-channel",
                release_channel,
                "--output-path",
                str(resolved_tag_path),
            ]
            if args.custom_tag.strip():
                resolve_args.extend(["--custom-tag", args.custom_tag.strip()])
            run_command(resolve_args, repository_path, "Подбор релизного тега")

            resolved_tag_report = load_json(resolved_tag_path)
            resolved_tag = str(resolved_tag_report.get("resolvedTag") or "").strip()
            if not resolved_tag:
                raise ValueError("Не удалось определить релизный тег для режима full.")

            run_command(
                [
                    sys.executable,
                    str(scripts_dir / "set-version.py"),
                    "--version-tag",
                    resolved_tag,
                    "--repository-path",
                    str(repository_path),
                ],
                repository_path,
                "Обновление Version64",
            )

            report["actions"]["tagRequired"] = True
            report["actions"]["releaseTriggered"] = True
            report["actions"]["tagName"] = resolved_tag

        state["upstream"]["english_xml_url"] = report["upstream"]["englishXmlUrl"]
        state["upstream"]["last_processed_sha256"] = report["upstream"]["currentSha256"]
        state["upstream"]["last_processed_commit_sha"] = head_sha
        state["upstream"]["last_processed_at"] = get_now_iso()
        state["upstream"]["last_seen_etag"] = report["upstream"]["etag"]
        state["upstream"]["last_seen_last_modified"] = report["upstream"]["lastModified"]
        if resolved_tag:
            state["release"]["last_tag"] = resolved_tag
            state["release"]["last_release_commit"] = head_sha
        write_json(state_path, state)
        report["actions"]["stateUpdated"] = True

        changed_files = git_changed_files(repository_path)
        report["git"]["changedFiles"] = changed_files
        report["actions"]["commitRequired"] = bool(changed_files)

        if changed_files:
            commit_message = build_commit_message(
                changed_files=changed_files,
                upstream_sha256=report["upstream"]["currentSha256"],
                mode=args.mode,
                summary=report["summary"],
                usage=report["usage"],
            )
            commit_message_path.parent.mkdir(parents=True, exist_ok=True)
            commit_message_path.write_text(commit_message, encoding="utf-8")

        report["status"] = "success"
        report["reason"] = "Обработка завершена успешно."
        write_json(run_report_path, report)
    except Exception as exc:
        report["status"] = "error"
        report["reason"] = "Автопилот завершился ошибкой."
        report["error"] = {
            "message": str(exc),
        }
        report["summary"] = read_summary(output_dir)
        report["usage"] = read_usage(output_dir)
        report["git"]["changedFiles"] = git_changed_files(repository_path)
        write_json(run_report_path, report)
        print(exc, file=sys.stderr)
        return 1

    print(
        "[run-autopilot.py] "
        f"Mode={args.mode}; ChangedFiles={len(report['git']['changedFiles'])}; "
        f"Tag={report['actions']['tagName'] or 'n/a'}."
    )
    print(f"[run-autopilot.py] Report written to '{run_report_path}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
