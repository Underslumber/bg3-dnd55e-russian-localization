# AGENT Common Rules

Reusable baseline rules that are not tied to this repository.

## Communication (MUST)
- Answer first, then request approval if needed.
- Concise, meaningful, no filler.
- Do not end response with only procedural choice.
- In scenarios where local configuration, secrets, or notification settings may be needed, automatically check and use `.env.local` when it exists and is relevant; if it is missing but clearly required, state that once, use `.env.example` as the schema when available, and name the required keys without inventing values; never commit `.env.local` or print secret values.

Approval/clarification:
- ask once, no repetition
- binary -> yes/no
- multiple -> numbered options + brief context
- ask dependent questions sequentially, not in one message
- if one decision changes or gates the next step, ask the prerequisite decision first and wait for the answer before asking the next one
- do not combine branch selection with operational approval in the same message

Formatting:
- File links in repo docs/checklists: relative paths, `/`, spaces as `%20`.
- In assistant UI responses, use the link format required by the execution environment; include relative path text when possible.
- External links in assistant UI responses: use markdown links with a clear label, not bare URLs.

## Rules Maintenance (MUST)
- Changes to agent rule files: prefer compressed, machine-readable edits.
- Keep updates minimal and non-duplicative: merge overlapping points, remove redundancy, preserve intent.
