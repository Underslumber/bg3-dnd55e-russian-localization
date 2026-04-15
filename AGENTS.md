# AGENTS.md

## Execution Model (MUST)
- Read this file first; treat as system-level constraints.
- Reusable general rules (MUST read and apply): [AGENT.common.md](AGENT.common.md)
- Reusable structured interaction rules (MUST read and apply for agent-initiated user-facing questions, approvals, clarifications, confirmations, and branch/action choices): [AGENT.interaction.md](AGENT.interaction.md)
- Skills (slash-команды для типовых задач): [.skills/](.skills/) — `/translation-update`, `/translation-tools`, `/meta-sync`
- Priority:
  1. User instructions
  2. AGENTS.md
  3. Applicable referenced reusable rule files
  4. Existing code/style
  5. Best practices
- Response language: Russian (commit messages, answers, changelogs, all agent output).
- Code style: prefer minimal, non-breaking changes; do not introduce unnecessary abstractions.

---

## Git Workflow (MUST)
- Never commit/push without explicit user approval.
- After approval → commit + push immediately.
- Commit messages: Russian, factual (what was done).
- Branch (`fix/*` or `feat/*`): ask once before the first file-changing task that may lead to commit; reuse decision for all subsequent tasks in same dialogue.
- Branch selection question MUST use `AGENT.interaction.md` format.
- If branch selection is required, ask for it in a separate message before any follow-up question about running scripts, applying changes, or other operational actions.
- Do not combine branch choice with script/action approval in one message.

After work in `fix/*` or `feat/*`:
1. create PR/MR targeting `main`
2. merge changes into `main` and delete the source branch

Push failure:
- retry ≤2 times, 3s delay

Release link:
- provide `[version](url)` immediately after tag push, without waiting for CI

---

## Scope (MUST)
- Repo = Russian localization mod only.

Allowed:
- localization content
- packaging/release metadata

Forbidden:
- gameplay logic
- Script Extender
- unrelated assets

- Repo must remain source-only.
- Never commit `.pak` or build artifacts.

---

## Project Structure (MUST)

Canonical paths:
- Mod: `Mods/DnD 5.5e AIO Russian`
- Localization: `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
- Metadata: `Mods/DnD 5.5e AIO Russian/meta.lsx`
- Build: `scripts/build.ps1` _(single source of build truth)_
- CI: `.gitea/workflows/build.yml`
- Official glossary: `glossary/glossary.official.json` _(primary terminology reference; MUST read first when working on translations)_
- Secondary glossary: `glossary/glossary.normalized.json` _(secondary/fallback terminology reference; use only after `glossary/glossary.official.json` and do not override official terminology with it)_
- Local env template: `.env.example`
- Local env file: `.env.local`

Top-level repository layout:
- `.cache/` → local cache/workdir data; never package
- `.git/` → local VCS metadata; never package
- `.gitea/` → CI and release workflows
- `.github/` → GitHub metadata/workflows when present
- `.tools/` → local tooling; never package
- `build/` → generated outputs only; never commit release artifacts
- `glossary/` → terminology reference
- `Mods/` → mod sources only
- `scripts/` → build/release/support scripts
- `.env.example` → local env schema
- `.env.local` → local machine config/secrets; never commit — keys: `OPENROUTER_API_KEY`, `TG_BOT_TOKEN`, `TG_CHAT_ID`, `TG_THREAD_ID`, `AUTOPILOT_MODE`, `AUTOPILOT_DEFAULT_RELEASE_CHANNEL`
- `.gitignore` → ignore policy
- `AGENT.common.md` → reusable general agent rules
- `AGENT.interaction.md` → reusable structured interaction rules
- `AGENTS.md` → project-specific agent contract
- `LICENSE` → license metadata
- `README.md` → project overview

Upstream EN reference:
- [english.xml](https://github.com/Yoonmoonsik/dnd55e/blob/main/Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml)

---

## Packaging (MUST)
- `.pak` contains ONLY `Mods/...`

Required:
- `meta.lsx`
- `russian.xml`

Forbidden in `.pak`:
- `.git`, `.gitea`
- `scripts`, `tools`, `.tools`
- `build`, staging dirs

Staging:
- use `%TEMP%`
- not inside repo

---

## Build & CI (MUST)
Flow:
1. prepare
2. download Divine
3. run `scripts/build.ps1`
4. publish

Outputs:
- `build/*.pak`
- `build/info.json`
- `build/*.zip` (tag only)

Release ZIP:
- only `.pak` + `info.json`

Triggers:
- automatic: push tag `v*`
- manual: workflow_dispatch
- branch pushes without tag MUST NOT publish release artifacts

Notifications:
- Telegram sent automatically by CI via `scripts/send-telegram-notification.ps1`
- on build start, success, and failure (tag builds only)
- requires `TG_BOT_TOKEN`, `TG_CHAT_ID`, `TG_THREAD_ID` secrets

---

## Versioning (CRITICAL)
Source of truth:
`ModuleInfo/Version64` — read via explicit XML parsing:
`save/region[@id="Config"]/node[@id="root"]/children/node[@id="ModuleInfo"]/attribute[@id="Version64"]`

Rules:
- do not change `PublishVersion`
- tag MUST match version
- tag formats:
  - stable: `vX.Y.Z` -> `Version64 = X.Y.Z.0`
  - suffixed: `vX.Y.Z-suffix` -> `Version64 = X.Y.Z.N`
- for suffixed tags, suffix affects tag/release channel only and is NOT encoded in `Version64`
- for suffixed tags on the same base version `X.Y.Z`, increment `build` (`N`) by running `git tag --list "vX.Y.Z-*"` and counting prior released tags; current release uses next value starting from `1`
- stable tag without suffix always uses `build = 0`, even if suffixed releases for the same base version already existed

Before tag:
1. if version already changed → use it
2. if same as last → bump:
   `python scripts/set-version.py -VersionTag <tag>`

`build.ps1`:
- derives version from tag
- writes to `info.json` + staged `meta.lsx`

Conflict resolution (MUST):
- before release, `Version64` in `meta.lsx` MUST equal target tag version
- if mismatch, run `python scripts/set-version.py -VersionTag <tag>` and re-check
- if still mismatch, release is blocked

---

## info.json (MUST)
Root:
- `Mods`, `MD5`

Per mod:
- Author, Name, Folder, Version
- Description, UUID, Created
- Dependencies (array), Group

Dependency UUID:
`897914ef-5c96-053c-44af-0be823f895fe`

---

## Guardrails (MUST)

Before commit:
- scope valid (localization/metadata only)
- no forbidden content
- no build artifacts (`.pak`, `build/`, `.cache/`, staging)
- no temp/debug artifacts; ignored patterns MUST be present in `.gitignore`: `build/`, `build-stage*`, `.tools/`, `.cache/`, `*.pak`
- packaging invariants intact
- version consistent (if applicable)

Before release:
- version == tag
- version bumped if needed
- CI/build contract valid
- outputs correct (no extra files)

---

## Release & Changelog (MUST)

- Every release MUST include changelog.

Changelog rules:
- language: Russian; concise, user-facing; describe WHAT changed; group logically
- source: prefer real diff over commits; inspect actual file changes
- `russian.xml` changes: summarize added/changed/removed strings with user-visible impact
- metadata/CI changes: describe effect, not raw edits
- large diff: group + summarize
- no visible changes: state "техническое обновление"
- do not invent changes; do not include internal noise

Approval gates:
- Gate A: explicit approval for commit/push
- Gate B: explicit approval for release publish (after changelog draft)

Release message includes: version, changelog, `[version](url)` if derivable.

---

## Release Verification (MUST)
- verification_order: `workflow_status -> release_presence -> assets_presence -> asset_name`
- asset_name_template: `DnD 5.5e AIO Russian <tag>.zip` (e.g. `DnD 5.5e AIO Russian v1.2.3.zip`)
- source_of_truth: `workflow/release API data`; exact asset filename only if read from build/workflow output
- wait_cycle_max: `30s`
- passive_wait_total_max: `120s` unless user explicitly requested a longer wait
- after_each_wait_cycle: emit user-visible status
- asset_name_mismatch: stop waiting; report actual asset name
- workflow_success_missing_asset: stop waiting; report `release_url`, `workflow_url`, `asset_list`
