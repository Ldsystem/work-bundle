---
name: ks-guard-scope
description: 'Enforce knowledge write scope, sensitivity, and safety boundaries.'
---

# ks-guard-scope

## Scope

Enforce knowledge write scope, sensitivity, and safety boundaries.

## Workflow Reference

Use `references/ks-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/ks-directives/guard-scope.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `references/rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `references/rules/ks-persistence-gate.yaml`
- `ks-sensitivity-filter`: `references/rules/ks-sensitivity-filter.yaml`
- `ks-off-switches`: `references/rules/ks-off-switches.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/ks-directives.md`
- `references/ks-perspectives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
