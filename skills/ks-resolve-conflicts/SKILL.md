---
name: ks-resolve-conflicts
description: 'Resolve duplicate or conflicting durable knowledge notes with canonical ownership.'
---

# ks-resolve-conflicts

## Scope

Resolve duplicate or conflicting durable knowledge notes with canonical ownership.

## Workflow Reference

Use `references/ks-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/ks-directives/resolve-conflicts.md` for directive-specific behavior.

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
