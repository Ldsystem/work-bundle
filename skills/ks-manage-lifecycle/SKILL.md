---
name: ks-manage-lifecycle
description: 'Change durable note lifecycle status using valid evidence.'
---

# ks-manage-lifecycle

## Scope

Change durable note lifecycle status using valid evidence.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/keep-summarizing/manage-lifecycle.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `rules/ks-persistence-gate.yaml`
- `ks-perspective-routing`: `rules/ks-perspective-routing.yaml`
- `ks-sensitivity-filter`: `rules/ks-sensitivity-filter.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/directives/keep-summarizing/index.md`
- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
