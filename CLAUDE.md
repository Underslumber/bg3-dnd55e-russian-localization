# CLAUDE.md

Entry point for Claude Code. Rules SSOT — [AGENTS.md](AGENTS.md), read before any task.

- This file and AGENTS.md are maintained in English, machine-first format.

## Project
- Russian localization mod **DnD 5.5e All-in-One BEYOND** for Baldur's Gate 3.
- Source-only: `.pak` and build artifacts are never committed.
- Upstream EN: [english.xml](https://github.com/Yoonmoonsik/dnd55e/blob/main/Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml)
- Response/commit language: Russian.
- Skills: [.agents/skills/](.agents/skills/) — `/translation-update`, `/meta-sync`.

## Translation pipeline
Run from repo root.

```bash
# 1. fetch upstream english.xml
python .agents/skills/translation-update/scripts/get-upstream-english.py

# 2. diff → build/translation-diff/
python .agents/skills/translation-update/scripts/compare-translation.py

# 3. fill build/translation-diff/candidates.json manually

# 4. apply candidates
python .agents/skills/translation-update/scripts/apply-translation-edits.py --edits-path build/translation-diff/candidates.json

# 5. validate XML
python scripts/validate-translation-xml.py --xml-path "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml"

# OpenRouter pipeline (separate)
python scripts/fill-translation-openrouter.py
python scripts/update-translation-openrouter.py
```

Outputs: `build/translation-diff/{summary.json,summary.md,candidates.json}`.

## Autopilot
`.github/workflows/autopilot-sync.yml`, scheduled. Modes and variables — [docs/autopilot.md](docs/autopilot.md).
