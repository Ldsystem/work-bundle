---
id: ks-structural-value
applies_when:
  - candidate durable point is evaluated
enforcement: must
load: conditional
requires: []
---

# Ks Structural Value

## Purpose

- Define the hard gate for deciding whether a candidate point is durable enough to persist as knowledge.
- Prevent low-value, temporary, or unsafe material from entering the durable knowledge base.

## Must

- Persist a candidate point only when at least one of these structural-value reasons is true:
  - It changes a stable design.
  - It clarifies a reusable process flow.
  - It clarifies a reusable data flow.
  - It clarifies architecture, module boundaries, or deployment shape.
  - It defines a code-structure convention.
  - It records an important decision or rejected option.
  - It captures a reusable pattern.
  - It affects future implementation choices.
- Record the passing reason in the agent response or note draft before writing the note.
- Stop and ask if the passing reason is unclear.

## Must Not

- Do not save any of the following as durable knowledge:
  - one-off bugs
  - temporary errors
  - raw implementation logs
  - exploratory thoughts with no durable conclusion
  - guesses, wishes, or weak proposals as accepted knowledge
  - agent-generated open questions unless the user confirms they are valuable future work
  - credentials, tokens, personal data, or private keys
  - raw chat transcripts

## Validation

- Confirm at least one allowed structural-value reason applies before a write is prepared.
- Confirm the passing reason is stated explicitly in the response flow or note draft.
- Confirm the candidate does not match any disallowed item in this rule.

## On Violation

- Stop the write.
- Report that the candidate failed structural-value review, name the failing condition, and either discard the point or ask the minimum blocking question before continuing.
