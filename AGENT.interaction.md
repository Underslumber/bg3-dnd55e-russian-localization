# AGENT Interaction Rules (Experimental)

## 0. Structured Mode Activation

When structured interaction mode is active:

- The model MUST follow all rules in this document
- The model MUST NOT output reasoning, analysis, or progress updates
- The model MUST produce ONLY the question block
- The mode MUST be used for any agent-initiated user-facing choice, approval request, clarification, confirmation step, branch selection, or action selection
- Higher-priority instructions may also explicitly activate the mode for other question flows
- The mode remains active for the current question step and for each subsequent dependent question step until the decision flow is complete
- These rules apply to user-facing structured interaction output, not to internal tool usage or higher-priority system/developer constraints

Outside structured interaction mode, this document does not override normal interaction.

This is a strict mode, not a guideline.

---

## Purpose

This document defines strict interaction patterns for machine-first dialogs.  
Goal: eliminate ambiguity, minimize free-form input, and enforce deterministic flows.

---

## Core Principles

1. Option-first interaction
2. One question per step
3. Deterministic state transitions
4. Strict input validation
5. Minimal cognitive load

---

## 1. Question Format

All questions MUST follow this exact structure:

<Instruction>

1) Option A
2) Option B
3) Option C
4) Other

No additional sections are allowed.

---

## 2. Single Block Response Rule

The entire response MUST contain ONLY the question block.

Strictly forbidden:
- Any text before the question
- Any text after the question
- Answer instructions (e.g. "Answer:", "Single choice")
- Explanations
- Comments
- Status messages
- Summaries

---

## 3. Question-First Rule

The response MUST start directly with the instruction.

The first visible line MUST be the question instruction.

---

## 4. Output Shape (Strict)

Response MUST match exactly:

<Instruction>

1) ...
2) ...
3) ...

Nothing else is allowed.

---

## 5. Option-First Rule

- ALWAYS provide predefined options
- DO NOT ask open-ended questions unless:
  - user selected "Other"
  - or no reasonable option set exists

---

## 6. One Question Rule

NEVER combine multiple questions.

❌ Invalid:
"Choose service type and database"

✅ Valid:
Step 1 → service type  
Step 2 → database

---

## 7. Step-by-Step Execution

The interaction MUST behave as a state machine.

Example:

STATE FLOW:
service_type → database → architecture → confirmation

Rules:
- Do not skip steps
- Do not ask next question before receiving valid input

---

## 8. Input Validation

If input is invalid:

- DO NOT proceed
- Repeat the same question
- Show valid options again

---

## 9. Validation Strictness

- Partial matches are invalid
- Text + number is invalid
- Out-of-range values are invalid
- Empty input is invalid

No auto-correction allowed  
No intent interpretation allowed

---

## 10. Option Limits

- Max 5–7 options per question
- If more options exist:
  → split into multiple steps

---

## 11. "Other" Handling

If "Other" is selected:

1) Ask for free-form input
2) Treat response as final
3) Do not re-offer options

---

## 12. Multiple Choice Rules

If multiple choice is required:
- clearly indicate it in the instruction
- expected format: 1,3,5

Do NOT add separate answer blocks.

---

## 13. Confirmation Step (Mandatory)

Final step MUST be:

Summary:

- Field A: value
- Field B: value

1) Confirm
2) Restart
3) Edit specific step

---

## 14. Response Contract

Expected user input:
- 1
- 2
- 1,3

Forbidden:
- "I choose 2"
- "Option 1"
- "Probably 3"

Invalid input MUST be rejected.

---

## 15. Error Recovery

If input is invalid:

- Do not interpret
- Do not guess
- Repeat question exactly

---

## 16. Retry Strategy

1st attempt:
- Show error
- Repeat options

2nd attempt:
- Show error
- Emphasize format

3rd attempt:
- Minimal hint

Never relax rules.

---

## 17. No Reasoning Output (Strict)

Reasoning output is strictly forbidden.

Disallowed:
- analysis
- planning
- status updates
- progress logs
- explanations of actions

If reasoning is generated internally:
- it MUST NOT appear in the response

---

## 18. Brevity Constraint

- Output must be compact
- Must fit without scrolling
- No extra lines

---

## 19. Deterministic Behavior Rules

- Same input → same output
- Option order must not change
- No randomness
- No rephrasing of options

---

## 20. Execution Boundary

The model is responsible only for:
- rendering the question
- enforcing answer format

The system is responsible for:
- state
- transitions
- validation
- retries

The model MUST NOT:
- track state
- skip steps
- reorder flow

---

## 21. Step Completion Rule

A step is complete only when:
- input is valid
- value is parsed

Otherwise:
- stay on the same step

---

## 22. No Implicit Defaults

The model MUST NOT:
- assume values
- auto-fill fields
- skip questions

---

## 23. Compact Mode (Optional)

If user provides:

service=1 db=2 arch=3

Then:
- parse values
- skip completed steps
- go to confirmation

If partial:
- apply valid values
- continue flow

---

## 24. Violation Handling

If the model produces non-compliant output:

- discard the response
- regenerate using strict format

---

## 25. Priority

Within active structured interaction mode, these rules override normal conversational behavior.

Priority:
1. Determinism
2. Structure
3. Format compliance
4. User convenience
