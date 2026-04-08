# AGENTS.md

## Project Overview

This repository contains a standalone Russian localization mod for **Baldur's Gate 3**:

- Mod name: `DnD 5.5e All-in-One BEYOND Russian Localization`
- Mod folder: `Mods/DnD 5.5e AIO Russian`
- Base/original mod dependency: `DnD 5.5e All-in-One BEYOND`
- Original mod repository: `https://github.com/Yoonmoonsik/dnd55e`
- Original dependency UUID: `897914ef-5c96-053c-44af-0be823f895fe`

This repository is for the localization mod only. It must not gain gameplay logic, Script Extender files, or unrelated assets.

## Repository Rules

- Keep the repository source-only.
- Do not commit `.pak` artifacts.
- Do not commit temporary build outputs.
- Do not add gameplay or script content unrelated to localization/release packaging.
- Keep the localization folder and metadata consistent with the packaged mod.

## Current Important Paths

- Mod sources: `Mods/DnD 5.5e AIO Russian`
- Localization XML: `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`
- Mod metadata: `Mods/DnD 5.5e AIO Russian/meta.lsx`
- CI workflow: `.gitea/workflows/build.yml`
- Main build script: `scripts/build.ps1`

## Build And Release Model

The authoritative build logic lives in:

- `scripts/build.ps1`

The Gitea workflow should stay thin and only:

1. prepare the workspace
2. download `Divine`
3. call `scripts/build.ps1`
4. publish the release zip for tag builds

### Current Build Outputs

The build script produces:

- `build/DnD 5.5e AIO Russian.pak`
- `build/info.json`
- `build/DnD 5.5e AIO Russian <tag>.zip` for tagged builds

The release zip is expected to contain:

- the built `.pak`
- `info.json`

## Packaging Notes

The package must contain only the BG3 mod structure under `Mods/...`.

Verified expected extracted `.pak` structure:

- `Mods/DnD 5.5e AIO Russian/meta.lsx`
- `Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml`

Do not allow `.git`, `.gitea`, `scripts`, `tools`, `.tools`, `build`, or staging directories into the `.pak`.

## Important Packaging Behavior

There is a runner-specific packaging quirk:

- `Divine` can produce a broken 48-byte `.pak` on the CI runner depending on the source path.
- Current mitigation is implemented in `scripts/build.ps1`.
- The script uses staged sources and fallback packaging attempts.
- Staging is performed in `%TEMP%`, not in a dot-prefixed directory inside the repo.

If packaging breaks again, debug the source path and unpack the resulting `.pak` locally to verify actual contents.

## Versioning

Version displayed by BG3ModManager should be derived from the release tag.

Current behavior:

- `scripts/build.ps1` derives `Version64` from tags like `v0.1.0`
- the computed version is written into:
  - generated `info.json`
  - staged `meta.lsx` before packaging

Do not manually hardcode release versions in the committed `meta.lsx` for each release if CI can derive them from tags.

## info.json Expectations

`info.json` is generated during build and should remain aligned with BG3/BG3ModManager expectations.

Current expected shape:

- top-level `Mods`
- top-level `MD5`
- per-mod fields:
  - `Author`
  - `Name`
  - `Folder`
  - `Version`
  - `Description`
  - `UUID`
  - `Created`
  - `Dependencies`
  - `Group`

Current dependency model:

- `Dependencies` is an array of dependency UUIDs
- current dependency UUID:
  - `897914ef-5c96-053c-44af-0be823f895fe`

## CI Trigger Policy

Current workflow policy:

- run on tags `v*`
- run on manual dispatch
- do not run on every push to `main`

## Git / Collaboration Preferences

User preference:

- after making changes, ask for permission before committing
- if the user approves, commit and push immediately
- for significant changes, propose moving work into a separate branch
- feature/fix branches must use the prefix `feat/` or `fix/`
- after finishing work in a `feat/` or `fix/` branch, propose merging it back into `main`
- comments and commit messages should be written in Russian
- commit messages should describe what was done, not what should be done
- if changes affect files that go into the final `.pak`, or change the build/release process, propose releasing the next version
- if push fails, retry up to two more times with a 3-second pause between attempts

Do not auto-commit or auto-push without explicit user approval.

## Cleanup Expectations

Temporary directories and debug artifacts should not remain in the repository.

Ignored paths currently include:

- `build/`
- `build-stage*`
- `.tools/`
- `*.pak`

If local debugging creates additional temporary folders, remove them when done unless the user explicitly wants to keep them.
