# AGENTS.md

SSOT for project rules. [CLAUDE.md](CLAUDE.md) points here.

## Meta
- This file and CLAUDE.md are maintained in English, machine-first format.
- machine-first: dense bullets, key: value, no prose, no decorative markup.
- Response/commit/changelog language is controlled separately (see Interaction).

## Interaction
- User questions — use host-native interactive tool (`AskUserQuestion`, `question`, equivalents). No tool available — use numbered list.
- One decision per question. Dependent decisions — sequential.
- Numbered-list question format: intro line + `1.`/`2.`/`3.` options only; no trailing summary/request in a separate assistant message.
- If clarification is required, put it into the intro line before the options, not after them.
- Do not combine branch selection with operational confirmation.
- Ask once; reuse the answer within the session.
- Short status updates are allowed and expected.
- Response/commit/changelog language: Russian.

## Git
- Commit/push only after explicit user approval; after approval — immediately.
- Commit message: Russian, factual.
- Branches: `fix/*`, `feat/*`. Branch choice — once, before first file-changing task.
- After `fix/*`/`feat/*` branch work: offer either merge into `main` + delete branch, or create PR.
- Rule above does not apply outside `fix/*`/`feat/*` branches.
- Push retry: ≤2, delay 3s.
- After tag push — immediately emit `[version](url)`, do not wait for CI.

## Scope
- Allow: localization content, packaging/release metadata.
- Deny: gameplay logic, Script Extender, unrelated assets, `.pak`, build artifacts.
- Repo is source-only.

## Paths
- mod: `Mods/DnD 5.5e AIO Russian`
- localization: `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
- metadata: `Mods/DnD 5.5e AIO Russian/meta.lsx`
- build_script: `scripts/build.ps1` (single build source of truth)
- ci: `.github/workflows/build.yml`
- glossary_primary: `glossary/glossary.official.json` (read first)
- glossary_fallback: `glossary/glossary.normalized.json` (does not override official)
- env_schema: `.env.example`
- env_local: `.env.local` (never commit)
- skills: `.agents/skills/` — `/translation-update`, `/meta-sync`
- upstream_en: https://github.com/Yoonmoonsik/dnd55e/blob/main/Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml

Top-level (never package): `.git`, `.github`, `.cache`, `.tools`, `build`, staging.

## Translation
- `translation-update`: agent skill; uses skill-local scripts in `.agents/skills/translation-update/`; does not call `scripts/update-translation-openrouter.py`
- `scripts/update-translation-openrouter.py`: separate OpenRouter pipeline; not part of `translation-update`

## Secrets
- `.env.local` keys: `OPENROUTER_API_KEY`, `TG_BOT_TOKEN`, `TG_CHAT_ID`, `TG_THREAD_ID`, `AUTOPILOT_MODE`, `AUTOPILOT_DEFAULT_RELEASE_CHANNEL`.
- Auto-load when present. If missing but required — mention once, reference `.env.example`, list required keys.
- Never: invent values, print secrets, commit `.env.local`.

## Packaging
- `.pak` contains only `Mods/...`.
- Required: `meta.lsx`, `russian.xml`.
- Forbidden in `.pak`: `.git`, `scripts`, `tools`, `.tools`, `build`, staging.
- Staging — in `%TEMP%`, not inside repo.

## Build & CI
- Flow: prepare → download Divine → `scripts/build.ps1` → publish.
- Outputs: `build/*.pak`, `build/info.json`, `build/*.zip` (tag only).
- Release ZIP: only `.pak` + `info.json`.
- Triggers: tag `v*` (auto), `workflow_dispatch` (manual). Push without tag — no release artifacts.
- Telegram: `scripts/send-telegram-notification.ps1`, on start/success/failure for tag builds. Requires `TG_BOT_TOKEN`, `TG_CHAT_ID`, `TG_THREAD_ID`.

## Versioning
- SSOT: `ModuleInfo/Version64` via XPath `save/region[@id="Config"]/node[@id="root"]/children/node[@id="ModuleInfo"]/attribute[@id="Version64"]`.
- Do not change `PublishVersion`.
- Tag MUST == Version.
- Formats:
  - `vX.Y.Z` → `Version64 = X.Y.Z.0`
  - `vX.Y.Z-suffix` → `Version64 = X.Y.Z.N` (suffix affects tag/channel only, not Version64)
- `N` for suffixed: `git tag --list "vX.Y.Z-*"`, count prior + 1, starting from `1`.
- Stable tag (no suffix) always `build = 0`.
- Before tag: if version already bumped — use it; else `python scripts/set-version.py -VersionTag <tag>`.
- `build.ps1` derives version from tag, writes to `info.json` + staged `meta.lsx`.
- Conflict: `Version64` ≠ tag → run `set-version.py` → recheck; still ≠ → release blocked.

## info.json
- root: `Mods`, `MD5`
- per mod: `Author`, `Name`, `Folder`, `Version`, `Description`, `UUID`, `Created`, `Dependencies[]`, `Group`
- dependency UUID: `897914ef-5c96-053c-44af-0be823f895fe`

## Guardrails
Pre-commit:
- scope valid (localization/metadata only)
- no forbidden content
- no build artifacts
- no temp/debug; `.gitignore` contains: `build/`, `build-stage*`, `.tools/`, `.cache/`, `*.pak`
- packaging invariants intact
- version consistent (if changed)

Pre-release:
- version == tag
- version bumped if needed
- CI/build contract valid
- outputs correct (no extra files)

## Release & Changelog
- Every release requires a changelog.
- Rules: Russian, concise, user-facing, describe WHAT changed, group logically.
- Source: real diff > commits.
- `russian.xml`: summarize added/changed/removed with user-visible impact.
- meta/CI: describe effect, not raw edits.
- Large diff: group + summarize.
- No visible changes: «техническое обновление».
- Do not invent changes; do not include internal noise.
- Gates: A — commit/push, B — publish (after changelog draft).
- Release message: version, changelog, `[version](url)` if derivable.

## Release Verification
- order: `workflow_status → release_presence → assets_presence → asset_name`
- asset_name: `DnD 5.5e AIO Russian <tag>.zip` (e.g. `DnD 5.5e AIO Russian v1.2.3.zip`)
- source_of_truth: workflow/release API; exact filename only from build/workflow output
- wait_cycle_max: `30s`
- passive_wait_total_max: `120s` (longer only on explicit request)
- after_each_cycle: emit user-visible status
- asset_name_mismatch: stop, report actual name
- workflow_success_missing_asset: stop, report `release_url`, `workflow_url`, `asset_list`
