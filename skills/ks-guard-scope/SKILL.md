---
name: ks-guard-scope
description: 'Enforce knowledge write scope, sensitivity, and safety boundaries.'
---

# ks-guard-scope

## Scope

Enforce knowledge write scope, sensitivity, and safety boundaries.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/keep-summarizing/guard-scope.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `rules/ks-persistence-gate.yaml`
- `ks-sensitivity-filter`: `rules/ks-sensitivity-filter.yaml`
- `ks-off-switches`: `rules/ks-off-switches.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/directives/keep-summarizing/index.md`
- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
