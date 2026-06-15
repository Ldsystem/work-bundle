---
name: ks-manage-lifecycle
description: 'Change durable note lifecycle status using valid evidence.'
---

# ks-manage-lifecycle

## Scope

Change durable note lifecycle status using valid evidence.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Move notes between v3 statuses: `draft`, `proposed`, `confirmed`, `implemented`, `current`, `superseded`, `deprecated`, and `rejected`.

## Trigger phrases

- deprecate this note
- mark as draft
- supersede knowledge

## Use when

Lifecycle status should change with documented reason.

## Do not use when

Content change without status change (`ks-write-knowledge`).

## Workflow

1. Apply status transitions and promotion evidence per **Lifecycle Constraints (skill-owned)**.
2. Regenerate indexes via `ks-maintain-indexes`.
3. Recommend a commit when appropriate (see `ks-git-authority`).

## Return

- affected note paths
- old and new status
- reason recorded
- index rebuild status

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-perspective-routing`: `rules/keep-summarizing/ks-perspective-routing.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`
- `ks-git-authority`: `rules/keep-summarizing/ks-git-authority.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Lifecycle Constraints (skill-owned)

- Follow the v3 status ladder and `project.yaml` status rules (see loaded Runtime Rules).
- Preserve reasons and link replacements when superseding or deprecating.
- Require front matter evidence when promoting to `implemented` or promoting `current` from `implemented`.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
