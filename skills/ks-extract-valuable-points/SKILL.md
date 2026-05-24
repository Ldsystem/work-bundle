---
name: ks-extract-valuable-points
description: 'Extract durable candidate points from mixed source material before persistence.'
---

# ks-extract-valuable-points

## Scope

Extract durable candidate points from mixed source material before persistence.

## Workflow Reference

Use `references/ks-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/ks-directives/extract-valuable-points.md` for directive-specific behavior.

## Runtime Rules

- `ks-directive-selection`: `references/rules/ks-directive-selection.yaml`
- `ks-knowledge-boundary`: `references/rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `references/rules/ks-persistence-gate.yaml`
- `ks-structural-value`: `references/rules/ks-structural-value.yaml`
- `ks-sensitivity-filter`: `references/rules/ks-sensitivity-filter.yaml`
- `ks-off-switches`: `references/rules/ks-off-switches.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/ks-directives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
