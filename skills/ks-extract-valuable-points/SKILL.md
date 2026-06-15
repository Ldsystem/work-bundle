---
name: ks-extract-valuable-points
description: 'Extract durable candidate points from mixed source material before persistence.'
---

# ks-extract-valuable-points

## Scope

Extract durable candidate points from mixed source material before persistence.

## Role Context

Before directive-specific work, call `wb-select-role-context` to resolve the compact role_context for the current task, lifecycle stage, and perspective. Work under the selected stable role context; do not invent an ad hoc role.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/keep-summarizing/extract-valuable-points.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `rules/ks-persistence-gate.yaml`
- `ks-structural-value`: `rules/ks-structural-value.yaml`
- `ks-sensitivity-filter`: `rules/ks-sensitivity-filter.yaml`
- `ks-off-switches`: `rules/ks-off-switches.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/directives/keep-summarizing/index.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
