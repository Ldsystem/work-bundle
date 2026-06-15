---
name: ks-track-open-questions
description: 'Persist user-confirmed future-work watchpoints as accepted open questions.'
---

# ks-track-open-questions

## Scope

Persist user-confirmed future-work watchpoints as accepted open questions.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Track accepted unresolved project questions as standalone watchpoints under `open-questions/`.

## Trigger phrases

- record it for later
- we will resolve it later
- track this open question
- future problem to fix

## Use when

- the user provides a question as future work
- the user confirms an agent-proposed question should be tracked
- the user says `record it`, `we will resolve it later`, or similar

## Do not use when

Speculative questions the user has not accepted.

## Required inputs

- Question text and perspective.
- Trigger terms for future matching.
- User confirmation when the question was agent-proposed.

## Workflow

1. Run structural-value test (see `ks-structural-value`).
2. Write standalone note under `open-questions/<lifecycle-stage>/<perspective>/`.
3. Rebuild `indexes/open-question-registry.jsonl` via `ks-maintain-indexes`.

## Strict Rules

- Do not persist agent-generated questions without explicit user confirmation.
- Do not store open questions inside durable notes.
- Do not label an open question as a fact, decision, or rule.
- Use only leaf perspectives.
- Require trigger terms before completion.
- If confirmation or trigger terms are missing, return `Waiting for your direction`.

## Return

- open-question ID
- target path under `open-questions/`
- perspective
- trigger terms
- why it should be tracked
- whether indexes were rebuilt

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-open-question-policy`: `rules/keep-summarizing/ks-open-question-policy.md`
- `ks-note-state-authority`: `rules/keep-summarizing/ks-note-state-authority.md`
- `ks-index-maintenance`: `rules/keep-summarizing/ks-index-maintenance.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Boundary

Write only under `.work-bundle/knowledge/` allowed paths; redirect orchestration artifacts to orch-* skills.
