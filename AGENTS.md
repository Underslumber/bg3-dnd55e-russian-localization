# AGENTS.md

## General Rules (MUST)

### Git Collaboration Policy (General)
- Commit/push only after explicit user approval.
- After approval: commit and push immediately.
- Branch switch prompt (`fix/*` or `feat/*`): ask once at dialogue start; reuse the explicit user decision for all subsequent fix/feature tasks in the same dialogue.
- After finishing work in `fix/*` or `feat/*`: propose either
  1. creating an MR into `main`, or
  2. merging to `main` immediately and deleting the `fix/*`/`feat/*` branch.
- If push fails: retry up to 2 more times with 3s pause.
- Approval prompts for pending actions: short direct phrasing, no soft/opening phrases; response format is mandatory:
  - binary action: yes/no question.
  - multiple actions/combinations: numbered options only.

### Cleanup (General)
- Do not leave temporary/debug artifacts in repo.
- Remove additional debug/temp dirs unless user asked to keep them.

### Rules Maintenance (General)
- For changes to rules files (`AGENTS.md`, `ACTIONS.md`): prefer optimized, compressed edits for AI-agent execution (machine-readable, unambiguous).
- Keep rule updates minimal and non-duplicative: merge overlapping points, remove redundancy, preserve intent.

## Project-Specific Rules (MUST)

### Scope
- Repository purpose: standalone Russian localization mod only.
- Allowed domain: localization content + packaging/release metadata.
- Forbidden: gameplay logic, Script Extender content, unrelated assets.
- Keep repository source-only.
- Never commit `.pak` or temporary build artifacts.

### Canonical Paths
- Mod sources: `Mods/DnD 5.5e AIO Russian`
- Russian localization: `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
- Mod metadata: `Mods/DnD 5.5e AIO Russian/meta.lsx`
- Build script (single source of build truth): `scripts/build.ps1`
- CI workflow: `.gitea/workflows/build.yml`
- Glossary (primary terminology reference): `glossary/glossary.normalized.json`
- Action catalog and command playbooks: `ACTIONS.md`
- Upstream English reference: `https://github.com/Yoonmoonsik/dnd55e/blob/main/Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml`

### Packaging Invariants
- `.pak` must contain only BG3 mod structure under `Mods/...`.
- Required content in `.pak`:
  - `Mods/DnD 5.5e AIO Russian/meta.lsx`
  - `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
- Must not leak into `.pak`: `.git`, `.gitea`, `scripts`, `tools`, `.tools`, `build`, staging dirs.
- Staging for packaging must be in `%TEMP%`, not in dot-prefixed repo dirs.

### Build/CI Contract
- CI workflow stays thin:
  1. prepare workspace
  2. download Divine
  3. call `scripts/build.ps1`
  4. publish tag archive
- Expected build outputs:
  - `build/DnD 5.5e AIO Russian.pak`
  - `build/info.json`
  - `build/DnD 5.5e AIO Russian <tag>.zip` (for tag builds)
- Release ZIP must include only `.pak` + `info.json`.
- CI triggers: tag `v*` and manual dispatch; not every push to `main`.

### Version/Release Rules
- Read release version only from `save/region/node[@id="ModuleSettings"]/children/node[@id="ModuleInfo"]/attribute[@id="Version64"]` via explicit XML parsing.
- `PublishVersion` must not be changed during release preparation.
- Release tag must match the source-of-truth version.
- Decision logic before tagging:
  1. If `ModuleInfo/Version64` was manually changed (e.g. BG3 Toolkit), use matching tag and release.
  2. If `ModuleInfo/Version64` equals latest released version, bump version first (e.g. `scripts/set-version.ps1 -VersionTag <tag>`), commit, then create/push tag.
- `scripts/build.ps1` derives release `Version64` from tag and writes it to generated `info.json` and staged `meta.lsx`.

### info.json Contract
- Top-level keys: `Mods`, `MD5`.
- Per-mod keys: `Author`, `Name`, `Folder`, `Version`, `Description`, `UUID`, `Created`, `Dependencies`, `Group`.
- `Dependencies` is an array of UUIDs.
- Current dependency UUID: `897914ef-5c96-053c-44af-0be823f895fe`.

### Git Collaboration Policy (Project-Specific)
- Commit messages and comments: Russian.
- Commit message content: what was done (not what should be done).
- If changes affect `.pak` contents or build/release flow: propose releasing next version.
- For released versions in user-facing messages: provide direct archive link in Markdown format `[version](url)` when derivable (acceptable immediately after tag push, even before CI finishes).

### Cleanup (Project-Specific)
- Ignored/temp patterns include: `build/`, `build-stage*`, `.tools/`, `*.pak`.
