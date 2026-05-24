---
name: ks-manage-lifecycle
description: 'Change durable note lifecycle status using valid evidence.'
---

# ks-manage-lifecycle

## Scope

Change durable note lifecycle status using valid evidence.

## Workflow Reference

Use `references/ks-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/ks-directives/manage-lifecycle.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `references/rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `references/rules/ks-persistence-gate.yaml`
- `ks-perspective-routing`: `references/rules/ks-perspective-routing.yaml`
- `ks-sensitivity-filter`: `references/rules/ks-sensitivity-filter.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/ks-directives.md`
- `references/ks-perspectives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
