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
2. Apply open-question policy per loaded `ks-open-question-policy`.
3. Complete watchpoint front matter per **Open Question Constraints (skill-owned)**.
4. Write standalone note under `open-questions/<lifecycle-stage>/<perspective>/`.
5. Rebuild `indexes/open-question-registry.jsonl` via `ks-maintain-indexes`.

## Strict Rules

Apply loaded Runtime Rules:

- Open-question confirmation and watchpoint policy: follow `ks-open-question-policy`
- Structural-value gate: follow `ks-structural-value`
- Knowledge path and scope: follow `ks-knowledge-boundary`
- Persistence gates: follow `ks-persistence-gate`
- Note and watchpoint state: follow `ks-note-state-authority`
- Index completion: follow `ks-index-maintenance`
- Sensitivity exclusions: follow `ks-sensitivity-filter`

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
- `ks-structural-value`: `rules/keep-summarizing/ks-structural-value.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Open Question Constraints (skill-owned)

- Use only leaf perspectives under `open-questions/<lifecycle-stage>/<perspective>/`.
- Require trigger terms in front matter before completion.
- Complete watchpoint front matter: question text, perspective, trigger terms, and tracking rationale.
- If trigger terms are missing, return `Waiting for your direction`.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
