---
name: ks-detect-structural-update
description: 'Decide whether material passes the structural-value gate for durable knowledge.'
---

# ks-detect-structural-update

## Scope

Decide whether material passes the structural-value gate for durable knowledge.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Decide whether a result is important enough to update the project knowledge repo.

## Trigger phrases

- should we save this
- is this worth documenting
- structural update

## Use when

Before persisting or when the user asks whether something belongs in the knowledge base.

## Do not use when

The user already gave a strong persist signal and details are clear (`write-knowledge` / `ks-write-knowledge`).

## Required inputs

- Candidate knowledge or change description.
- Source context.
- Candidate target perspective path from `references/assets/keep-summarizing/perspectives.md`.

## Workflow

1. Run the structural-value test from `workflow.md` and `ks-structural-value`.
2. Read `references/assets/keep-summarizing/perspectives.md` and verify perspective fit before deciding.
3. Reject container-only perspective targets; require a leaf perspective path.
4. Check granularity fit: one durable question per note candidate.
5. Check for duplicate durable facts already stored in another perspective.
6. Check whether implementation- or interface-shaped material contains domain semantics that need a domain, workflow, data, validation, or source-of-truth target.
7. Treat context-pack material as a source to decompose, not as canonical durable knowledge.
8. Assess risk of premature or wrong knowledge.
9. Recommend save, draft-only, or do not save.

## Decision Rules

- Return `save` only when the point passes the structural-value test and has a leaf perspective.
- Return `draft-only` when the point may matter later but is not accepted as current truth.
- Return `do-not-save` for temporary logs, raw chats, one-off bugs, weak guesses, secrets, credentials, personal data, or unsupported facts.
- If the target would overwrite or contradict a `current` note, return `ask-user`.
- If the candidate duplicates another `current` note, return `ask-user` unless a canonical note is already clear.
- If the candidate is a domain rule trapped in an implementation or interface note, return `save` only for the extracted semantic note target, not for another implementation-shaped duplicate.
- If the candidate comes from a context pack, return `save` only for decomposed atomic perspective notes.
- Weak approval is not enough for `current`.

## Return

- save, draft-only, do-not-save, or ask-user
- reason
- target leaf perspective path (or `none` if do not save)
- suggested update
- risk of saving wrong or premature knowledge

## Runtime Rules

- `ks-structural-value`: `rules/keep-summarizing/ks-structural-value.md`
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
