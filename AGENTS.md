# AGENTS.md

## Execution Model (MUST)
- Read this file first; treat as system-level constraints.
- Reusable general rules (MUST read and apply): [AGENT.common.md](AGENT.common.md)
- Reusable structured interaction rules (MUST read and apply when structured interaction mode is active): [AGENT.interaction.md](AGENT.interaction.md)
- Priority:
  1. User instructions
  2. AGENTS.md
  3. Referenced reusable rule files
  4. Existing code/style
  5. Best practices
- Prefer minimal, non-breaking changes.
- Do not introduce unnecessary abstractions.

---

## Git Workflow (MUST)
- Never commit/push without explicit user approval.
- After approval → commit + push immediately.
- Commit messages: Russian, factual (what was done).
- Branch (`fix/*` or `feat/*`): ask once before the first file-changing task that may lead to commit; reuse decision for all subsequent tasks in same dialogue.

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
- Glossary: `glossary/glossary.normalized.json` _(primary terminology reference)_
- Actions: `ACTIONS.md`
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
- `.env.local` → local machine config/secrets; never commit
- `.gitignore` → ignore policy
- `ACTIONS.md` → project actions/checklists
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
- for suffixed tags on the same base version `X.Y.Z`, increment `build` (`N`) by counting prior released tags `vX.Y.Z-*`; current release uses the next value starting from `1`
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
- no build artifacts (`.pak`, `build/`, staging)
- no temp/debug artifacts; ignored patterns MUST be present in `.gitignore`: `build/`, `build-stage*`, `.tools/`, `*.pak`
- packaging invariants intact
- version consistent (if applicable)

Before push:
- explicit user approval
- commit message valid (RU, factual)

Before release:
- version == tag
- version bumped if needed
- CI/build contract valid
- outputs correct (no extra files)

---

## Release & Changelog (MUST)

- Every release MUST include changelog.

Changelog:
- language: Russian
- concise, user-facing
- describe WHAT changed
- group logically

Sources:
- prefer diff over commits

Diff rules:
- inspect real file changes

Localization (`russian.xml`):
- added / changed / removed strings
- summarize user-visible impact (UI, spells, descriptions)

Metadata / CI:
- describe effect, not raw edits

Large diff:
- group + summarize

If no visible changes:
- state "техническое обновление"

Before release:
- generate changelog draft
- ask for approval

Approval gates:
- Gate A: explicit approval for commit/push (code/content changes)
- Gate B: explicit approval for release publish (after changelog draft)

Release message:
- version
- changelog
- `[version](url)` if derivable

Do not:
- invent changes
- include internal noise

---

## Rules Maintenance (MUST)
- Changes to `AGENTS.md`, `ACTIONS.md`, or referenced reusable rule files: prefer compressed, machine-readable edits.
- Keep updates minimal and non-duplicative: merge overlapping points, remove redundancy, preserve intent.
