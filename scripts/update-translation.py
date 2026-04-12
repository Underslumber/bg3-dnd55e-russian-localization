#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Russian translation using prepared edits.")
    parser.add_argument(
        "-RussianPath",
        "--russian-path",
        default="Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
        dest="russian_path",
    )
    parser.add_argument("-EnglishPath", "--english-path", default=".cache/upstream/english.xml", dest="english_path")
    parser.add_argument("-OutputDir", "--output-dir", default="build/translation-diff", dest="output_dir")
    parser.add_argument("-EditsPath", "--edits-path", default="", dest="edits_path")
    return parser.parse_args()


def run_python_script(script_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(script_path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"Script failed: '{script_path}'.")
    return result


def main() -> int:
    args = parse_args()
    scripts_dir = Path(__file__).resolve().parent
    get_upstream_script_path = scripts_dir / "get-upstream-english.py"
    compare_script_path = scripts_dir / "compare-translation.py"
    apply_script_path = scripts_dir / "apply-translation-edits.py"

    try:
        for script_path in (get_upstream_script_path, compare_script_path, apply_script_path):
            if not script_path.exists():
                raise FileNotFoundError(f"Required script was not found: '{script_path}'.")

        resolved_output_dir = Path(args.output_dir).resolve()
        resolved_provided_edits_path = Path(args.edits_path).resolve() if args.edits_path.strip() else None

        with tempfile.TemporaryDirectory(prefix="bg3-translation-update-") as temp_dir:
            working_diff_dir = Path(temp_dir)

            run_python_script(
                get_upstream_script_path,
                ["--output-path", args.english_path, "--force"],
            )
            run_python_script(
                compare_script_path,
                [
                    "--english-path",
                    args.english_path,
                    "--russian-path",
                    args.russian_path,
                    "--output-dir",
                    str(working_diff_dir),
                ],
            )

            resolved_output_dir.mkdir(parents=True, exist_ok=True)
            for source_path in working_diff_dir.iterdir():
                destination_path = resolved_output_dir / source_path.name
                if (
                    resolved_provided_edits_path is not None
                    and destination_path.resolve() == resolved_provided_edits_path
                    and resolved_provided_edits_path.exists()
                ):
                    continue
                if source_path.is_dir():
                    shutil.copytree(source_path, destination_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(source_path, destination_path)

            summary_json_path = working_diff_dir / "summary.json"
            if not summary_json_path.exists():
                raise FileNotFoundError(f"Translation summary was not found: '{summary_json_path}'.")

            summary = json.loads(summary_json_path.read_text(encoding="utf-8"))
            has_diff = any(
                summary[key] > 0
                for key in (
                    "missingInRussianCount",
                    "versionMismatchCount",
                    "staleOnlyInRussianCount",
                )
            )

            if not has_diff:
                print("[update-translation.py] Перевод уже актуален, дополнительные действия не требуются.")
                return 0

            if not args.edits_path.strip():
                print(
                    "[update-translation.py] Найдены изменения перевода. Подготовьте правки в "
                    f"'{(resolved_output_dir / 'candidates.json').resolve()}' и затем запустите повторно с '-EditsPath'."
                )
                return 0

            effective_edits_path = Path(args.edits_path).resolve()
            if not effective_edits_path.exists():
                raise FileNotFoundError(f"Prepared edits file was not found: '{effective_edits_path}'.")

            run_python_script(
                apply_script_path,
                ["--russian-path", args.russian_path, "--edits-path", str(effective_edits_path)],
            )
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[update-translation.py] Обновление перевода завершено. Результат записан в "
        f"'{Path(args.russian_path).resolve()}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
