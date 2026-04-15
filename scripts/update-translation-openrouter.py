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
    parser = argparse.ArgumentParser(description="Update Russian translation using OpenRouter.")
    parser.add_argument(
        "-RussianPath",
        "--russian-path",
        default="Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
        dest="russian_path",
    )
    parser.add_argument("-EnglishPath", "--english-path", default=".cache/upstream/english.xml", dest="english_path")
    parser.add_argument("-OutputDir", "--output-dir", default="build/translation-diff", dest="output_dir")
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
        "-ReferenceRussianPath",
        "--reference-russian-path",
        default="",
        dest="reference_russian_path",
        help="Optional path to a reference Russian XML whose matching contentuid values should be reused directly.",
    )
    parser.add_argument(
        "-TrustedRegistryPath",
        "--trusted-registry-path",
        default="glossary/trusted-contentuid-versions.json",
        dest="trusted_registry_path",
        help="Path to trusted contentuid/version registry. Matching entries are skipped to save tokens.",
    )
    parser.add_argument("-BatchSize", "--batch-size", type=int, default=20, dest="batch_size")
    parser.add_argument("-MaxBatchChars", "--max-batch-chars", type=int, default=6000, dest="max_batch_chars")
    parser.add_argument("-Retries", "--retries", type=int, default=3, dest="retries")
    parser.add_argument(
        "--include-existing",
        action="store_true",
        dest="include_existing",
        help="Retranslate entries with already edited candidate text.",
    )
    parser.add_argument(
        "--from-scratch",
        action="store_true",
        dest="from_scratch",
        default=False,
        help=(
            "Pass --from-scratch to compare-translation.py: backs up and clears russian.xml, "
            "then retranslates all entries from scratch using OpenRouter."
        ),
    )
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


def copy_directory_contents(source_dir: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    for source_path in source_dir.iterdir():
        destination_path = destination_dir / source_path.name
        if source_path.is_dir():
            shutil.copytree(source_path, destination_path, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, destination_path)


def main() -> int:
    args = parse_args()
    scripts_dir = Path(__file__).resolve().parent
    get_upstream_script_path = scripts_dir / "get-upstream-english.py"
    compare_script_path = scripts_dir / "compare-translation.py"
    fill_script_path = scripts_dir / "fill-translation-openrouter.py"
    apply_script_path = scripts_dir / "apply-translation-edits.py"

    try:
        for script_path in (
            get_upstream_script_path,
            compare_script_path,
            fill_script_path,
            apply_script_path,
        ):
            if not script_path.exists():
                raise FileNotFoundError(f"Required script was not found: '{script_path}'.")

        resolved_output_dir = Path(args.output_dir).resolve()

        with tempfile.TemporaryDirectory(prefix="bg3-openrouter-update-") as temp_dir:
            working_diff_dir = Path(temp_dir)
            working_candidates_path = working_diff_dir / "candidates.json"

            run_python_script(
                get_upstream_script_path,
                ["--output-path", args.english_path, "--force"],
            )
            compare_args = [
                "--english-path",
                args.english_path,
                "--russian-path",
                args.russian_path,
                "--output-dir",
                str(working_diff_dir),
            ]
            if args.from_scratch:
                compare_args.append("--from-scratch")
            run_python_script(compare_script_path, compare_args)

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

            copy_directory_contents(working_diff_dir, resolved_output_dir)

            if not args.from_scratch and not has_diff:
                print("[update-translation-openrouter.py] Перевод уже актуален, дополнительные действия не требуются.")
                return 0

            fill_args = [
                "--candidates-path",
                str(working_candidates_path),
                "--english-path",
                args.english_path,
                "--russian-path",
                args.russian_path,
                "--output-path",
                str(working_candidates_path),
                "--batch-size",
                str(args.batch_size),
                "--max-batch-chars",
                str(args.max_batch_chars),
                "--retries",
                str(args.retries),
            ]
            if args.glossary_path.strip():
                fill_args.extend(["--glossary-path", args.glossary_path])
            else:
                fill_args.extend(["--official-glossary-path", args.official_glossary_path])
                if args.secondary_glossary_path.strip():
                    fill_args.extend(["--secondary-glossary-path", args.secondary_glossary_path])
            if args.reference_russian_path.strip():
                fill_args.extend(["--reference-russian-path", args.reference_russian_path])
            if args.trusted_registry_path.strip():
                fill_args.extend(["--trusted-registry-path", args.trusted_registry_path])
            if args.include_existing:
                fill_args.append("--include-existing")

            run_python_script(fill_script_path, fill_args)
            run_python_script(
                apply_script_path,
                ["--russian-path", args.russian_path, "--edits-path", str(working_candidates_path)],
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

            copy_directory_contents(working_diff_dir, resolved_output_dir)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[update-translation-openrouter.py] Обновление перевода через OpenRouter завершено. "
        f"Результат записан в '{Path(args.russian_path).resolve()}', кандидаты обновлены в '{resolved_output_dir}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
