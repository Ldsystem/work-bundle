---
name: ks-breakdown-design
description: 'Decompose design files into perspective-aligned durable knowledge notes.'
---

# ks-breakdown-design

## Scope

Decompose design files into perspective-aligned durable knowledge notes.

## Workflow Reference

Use `references/ks-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/ks-directives/breakdown-design.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `references/rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `references/rules/ks-persistence-gate.yaml`
- `ks-structural-value`: `references/rules/ks-structural-value.yaml`
- `ks-perspective-routing`: `references/rules/ks-perspective-routing.yaml`
- `ks-sensitivity-filter`: `references/rules/ks-sensitivity-filter.yaml`
- `ks-index-maintenance`: `references/rules/ks-index-maintenance.yaml`
- `ks-off-switches`: `references/rules/ks-off-switches.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/ks-directives.md`
- `references/ks-perspectives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
