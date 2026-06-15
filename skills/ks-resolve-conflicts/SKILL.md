---
name: ks-resolve-conflicts
description: 'Resolve duplicate or conflicting durable knowledge notes with canonical ownership.'
---

# ks-resolve-conflicts

## Scope

Resolve duplicate or conflicting durable knowledge notes with canonical ownership.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Resolve overlap or contradiction between curated notes.

## Trigger phrases

- conflicting notes
- merge these notes
- contradictory knowledge

## Use when

Two or more notes disagree or duplicate the same concept.

## Do not use when

There is no identified conflict; use `ks-write-knowledge` for straightforward updates.

## Required inputs

- Conflicting note paths or IDs.
- User preference when known.

## Workflow

1. Compare content and front matter.
2. Apply resolution workflow per **Conflict Resolution Constraints (skill-owned)**.

## Return

- decision taken or recommended
- affected paths
- whether user confirmation is required

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-perspective-routing`: `rules/keep-summarizing/ks-perspective-routing.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Conflict Resolution Constraints (skill-owned)

- Choose one resolution path: `merge`, `replace`, `create-new`, or `ask-user`.
- Do not silently overwrite contradictory `current` notes.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
