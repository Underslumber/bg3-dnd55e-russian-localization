# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Russian localization mod for **DnD 5.5e All-in-One BEYOND** (a Baldur's Gate 3 mod). The repo contains only source files — no `.pak` build artifacts are ever committed.

**Upstream EN reference:** [english.xml](https://github.com/Yoonmoonsik/dnd55e/blob/main/Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml)

---

## Agent Contract

**Read and apply these files before any task:**

- [AGENTS.md](AGENTS.md) — project-specific agent contract (scope, git workflow, versioning, packaging rules)
- [AGENT.common.md](AGENT.common.md) — communication and formatting rules
- [AGENT.interaction.md](AGENT.interaction.md) — structured interaction format for approvals and choices
- [.skills/](.skills/) — skills: `/translation-update`, `/translation-tools`, `/meta-sync`

**Response language:** Russian. **Commit messages:** Russian, factual.

---

## Key Paths

| Purpose | Path |
|---|---|
| Localization file | `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml` |
| Mod metadata | `Mods/DnD 5.5e AIO Russian/meta.lsx` |
| Official glossary (primary) | `glossary/glossary.official.json` |
| Secondary glossary (fallback) | `glossary/glossary.normalized.json` |
| Build script | `scripts/build.ps1` |
| CI workflow | `.gitea/workflows/build.yml` |
| Local env template | `.env.example` |
| Local secrets | `.env.local` (never commit) |

---

## Build

Build requires **LSLib Divine** on PATH or provided via `-DivinePath`:

```powershell
# Local build (no tag)
pwsh scripts/build.ps1

# Tagged build (sets Version64 and creates ZIP)
pwsh scripts/build.ps1 -VersionTag "v1.2.3"
```

Outputs go to `build/` — never commit them. Staging uses `%TEMP%` outside the repo.

---

## Translation Scripts

All scripts are in `scripts/`. Run from repo root.

```bash
# 1. Fetch upstream english.xml
python scripts/get-upstream-english.py

# 2. Compare with russian.xml → produces build/translation-diff/
python scripts/compare-translation.py

# 3. Fill candidates via OpenRouter (requires OPENROUTER_API_KEY in .env.local)
python scripts/fill-translation-openrouter.py

# 4. Apply filled candidates to russian.xml
python scripts/apply-translation-edits.py

# 5. Validate XML
python scripts/validate-translation-xml.py --xml-path "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml"

# Full update pipeline (steps 1-4 combined)
python scripts/update-translation-openrouter.py
```

Translation diff outputs: `build/translation-diff/summary.json`, `summary.md`, `candidates.json`.

---

## Versioning

Version source of truth: `Version64` attribute in `meta.lsx` at XPath:
`save/region[@id="Config"]/node[@id="root"]/children/node[@id="ModuleInfo"]/attribute[@id="Version64"]`

```bash
# Set version from tag
python scripts/set-version.py --version-tag v1.2.3
```

Tag formats: `vX.Y.Z` (stable, build=0) or `vX.Y.Z-suffix` (prerelease, build=N). Tag must match `Version64` before release.

---

## Autopilot (CI)

GitHub Actions workflow `.github/workflows/autopilot-sync.yml` runs on schedule. Modes: `off` / `sync_only` / `full`. Controlled via `AUTOPILOT_MODE` env variable. See [docs/autopilot.md](docs/autopilot.md) for full reference.

---

## Guardrails

**Never commit:** `.pak` files, `build/`, `.cache/`, `.tools/`, staging dirs, `.env.local`.

**Scope:** localization content and packaging metadata only. No gameplay logic, Script Extender, or unrelated assets.

**Before commit:** XML must be valid, no build artifacts, version consistent if changed.

**Before release:** version == tag, changelog required (Russian, user-facing, from real diff).
