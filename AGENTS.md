# AGENTS.md

Project-wide rules for coding agents. `CLAUDE.md` imports this file.

## Project
- Russian localization mod **DnD 5.5e All-in-One BEYOND** for Baldur's Gate 3.
- Response, commit, and changelog language: Russian.
- Repository scope: localization, mod metadata, source assets, build/release automation, tests, documentation, and agent skills.
- Do not add or modify upstream gameplay logic, Script Extender code, unrelated assets, `.pak` files, build outputs, or temporary files.

## Autonomy and Git
- Review, explain, diagnose, and plan requests are read-only unless the user also asks for changes.
- Change, fix, and build requests authorize safe in-scope local edits and non-destructive validation without additional confirmation.
- Ask only when an unresolved ambiguity would materially change the result or authorization is required.
- Never commit, push, create/push a tag, publish, or perform a destructive/external write without explicit user approval for that operation and the current scope.
- After approval, validate first and then perform the approved operation immediately.
- Commit messages: Russian and factual.
- After work on `fix/*` or `feat/*`, offer either merge into `main` with branch deletion or a PR. This does not apply on other branches.
- Push retries: at most 2 retries with a 3-second delay.

## Key paths
- localization: `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
- metadata: `Mods/DnD 5.5e AIO Russian/meta.lsx`
- build: `scripts/build.ps1`
- CI/release: `.github/workflows/build.yml`
- environment schema: `.env.example`
- official glossary: `glossary/glossary.official.json`
- fallback glossary: `glossary/glossary.normalized.json`

## Task routing
- Translation update requests: use `.agents/skills/translation-update/SKILL.md`.
- Parent metadata/dependency sync requests: use `.agents/skills/meta-sync/SKILL.md`.
- Release, tag, changelog, publication, or release-verification requests: use `.agents/skills/release/SKILL.md`.
- `scripts/update-translation-openrouter.py` is a separate OpenRouter pipeline and is not part of `translation-update`.

## Automation
- `.github/workflows/autopilot-sync.yml` syncs the upstream translation on a schedule and manually. In `full` mode it also commits and creates a release tag, which triggers `build.yml`.
- `.github/workflows/daily-translation-review.yml` reviews the translation daily and opens a draft PR into `main`.
- `.github/autopilot/state.json` holds the last processed upstream state and the release version policy. Read it before deriving a release version by hand.
- Modes, environments, secrets, and variables: `docs/autopilot.md`.

## Content and secrets
- Read the official glossary before translation work; the fallback glossary never overrides it.
- Treat `.env.example` and task-specific documentation as the configuration inventory; do not duplicate variable lists in agent instructions.
- Never invent, print, or commit secrets. `.env.local` is local-only and may be loaded only by scripts that explicitly support it.
- `scripts/build.ps1` is the packaging SSOT. Do not assemble `.pak` or release ZIP contents manually.
- `scripts/build.ps1 -VersionTag ...` updates the source `meta.lsx`; inspect and validate the resulting diff.

## Validation
- After file changes: run `python scripts/validate-repo.py --mode pre-commit` and relevant focused tests.
- Before commit: run `git diff --check`.
- Before a release: follow the `release` skill and run `python scripts/validate-repo.py --mode pre-release --version-tag <tag>`.
- Generated artifacts belong only in ignored `build/` or `%TEMP%`; never commit them.
