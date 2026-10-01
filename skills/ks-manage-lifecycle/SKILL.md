---
name: ks-manage-lifecycle
description: 'Decide and request an identified durable note status transition, supersession, or deprecation from accepted evidence. Excludes content-only updates and unresolved conflict diagnosis.'
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

1. Complete the shared workflow's agent decision preconditions, then choose the exact target status, evidence, and replacement links per **Lifecycle Constraints (skill-owned)**. Existing explicit transition intent needs no repeated permission request.
2. Prepare one complete `kind: note` request with `effect: transition`, `supersede`, or `deprecate`, exact canonical `path`, current `expected_digest`, complete target `record`, and `body`. Supersession/deprecation uses `superseded_by` references to already-existing replacement notes; identity, perspective, and creation date remain unchanged.
3. Invoke `python3 scripts/ks.py mutate-knowledge --project <slug> --request-file <request.yaml>`; optional `--dry-run` previews the one-record effect. The script checks mechanics and atomically replaces only that record; do not directly change front matter, move files, or patch indexes.
4. Report `old_status`, `status`, `canonical_status`, and `projection_status`. Consume successful rebuild evidence; for stale projections preserve the valid record and use the returned existing rebuild command.

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

Central `AGENTS.md` owns indexed rule discovery and exact-context body reuse. Consume carried task-local obligations in an accepted worker packet; these Runtime Rules are procedural pointers, not a separate loading algorithm.

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

## Self-check

- [ ] The agent settled value, relevance, authority, conflicts, sensitivity, evidence, and lifecycle intent before mutation.
- [ ] Exactly one note and current digest drive the request; replacement/evidence links are explicit and existing.
- [ ] The command applied the declared transition with no transcript, ad hoc file move, or second canonical-record effect.
- [ ] A stale projection is reported independently of the valid canonical record and semantic decision.
