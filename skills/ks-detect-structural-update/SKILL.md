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
3. Apply perspective routing, granularity, and domain-semantics checks per loaded `ks-perspective-routing`.
4. Check for duplicate durable facts already stored in another perspective per loaded `ks-perspective-routing`.
5. Treat context-pack material as a source to decompose, not as canonical durable knowledge.
6. Assess risk of premature or wrong knowledge.
7. Package the decision per **Structural Update Constraints (skill-owned)**.

## Decision Rules

Apply loaded Runtime Rules:

- Structural-value gate: follow `ks-structural-value`
- Perspective fit, leaf path, granularity, and domain routing: follow `ks-perspective-routing`
- Sensitivity exclusions: follow `ks-sensitivity-filter`

## Return

- save, draft-only, do-not-save, or ask-user
- reason
- target leaf perspective path (or `none` if do not save)
- suggested update
- risk of saving wrong or premature knowledge

## Runtime Rules

- `ks-perspective-routing`: `rules/keep-summarizing/ks-perspective-routing.md`
- `ks-structural-value`: `rules/keep-summarizing/ks-structural-value.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Structural Update Constraints (skill-owned)

- Return `save` only when all loaded Runtime Rules pass and durable persistence is warranted.
- Return `draft-only` when the point may matter later but is not accepted as current truth.
- Return `do-not-save` when loaded rules block persistence or the candidate fails structural-value review.
- Return `ask-user` if the target would overwrite or contradict a `current` note.
- Return `ask-user` if the candidate duplicates another `current` note unless canonical ownership is already clear.
- If the candidate comes from a context pack, return `save` only for decomposed atomic perspective notes.
- Weak approval is not enough for `current`.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
