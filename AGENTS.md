# AGENTS.md

## Execution Model (MUST)
- Read this file first; treat as system-level constraints.
- Priority:
  1. User instructions
  2. AGENTS.md
  3. Existing code/style
  4. Best practices
- Prefer minimal, non-breaking changes.
- Do not introduce unnecessary abstractions.

---

## Communication (MUST)
- Answer first, then request approval if needed.
- Concise, meaningful, no filler.
- Do not end response with only procedural choice.

Approval/clarification:
- ask once, no repetition
- binary → yes/no
- multiple → numbered options + brief context

- File links: relative paths, `/`, spaces as `%20`.

---

## Git Workflow (MUST)
- Never commit/push without explicit user approval.
- After approval → commit + push immediately.
- Commit messages: Russian, factual (what was done).

After work in `fix/*` or `feat/*`:
1. MR → main
2. merge → main + delete branch

Push failure:
- retry ≤2 times, 3s delay

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

## Paths (MUST)
- Mod: `Mods/DnD 5.5e AIO Russian`
- Localization: `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
- Metadata: `Mods/DnD 5.5e AIO Russian/meta.lsx`
- Build: `scripts/build.ps1`
- CI: `.gitea/workflows/build.yml`
- Glossary: `glossary/glossary.normalized.json`
- Actions: `ACTIONS.md`

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
- tag `v*`
- manual only

---

## Versioning (CRITICAL)
Source of truth:
`ModuleInfo/Version64`

Rules:
- do not change `PublishVersion`
- tag MUST match version

Before tag:
1. if version already changed → use it
2. if same as last → bump:
   `scripts/set-version.ps1 -VersionTag <tag>`

`build.ps1`:
- derives version from tag
- writes to `info.json` + staged `meta.lsx`

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

Release message:
- version
- changelog
- `[version](url)` if derivable

Do not:
- invent changes
- include internal noise