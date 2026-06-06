---
name: ks-what-is-helpful
description: 'Retrieve useful durable project knowledge for a concrete task without writing knowledge.'
---

# ks-what-is-helpful

## Scope

Retrieve useful durable project knowledge for a concrete task without writing knowledge.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/keep-summarizing/what-is-helpful.md` for directive-specific behavior.

## Runtime Rules

- `ks-directive-selection`: `rules/ks-directive-selection.yaml`
- `ks-knowledge-boundary`: `rules/ks-knowledge-boundary.yaml`
- `ks-context-pack-policy`: `rules/ks-context-pack-policy.yaml`
- `ks-open-question-policy`: `rules/ks-open-question-policy.yaml`
- `ks-note-state-authority`: `rules/ks-note-state-authority.yaml`
- `ks-sensitivity-filter`: `rules/ks-sensitivity-filter.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/directives/keep-summarizing/index.md`

## Retrieval Contract

- Discover relevant candidates across all allowed lifecycle partitions before lifecycle/status authority classification. Lifecycle does not pre-exclude discovery candidates.
- Apply visibility, sensitivity, and scope filters, then load full note bodies only for candidates that may materially affect the task.
- Classify validated candidates as `authority`, `candidate`, `background`, or `blocked`; only `authority` may directly shape downstream requirements, tasks, decisions, or review conclusions.
- Return the smallest useful classified result set rather than bulk-loading or dumping the knowledge base.

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
