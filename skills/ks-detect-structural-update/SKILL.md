---
name: ks-detect-structural-update
description: 'Decide whether material passes the structural-value gate for durable knowledge.'
---

# ks-detect-structural-update

## Scope

Decide whether material passes the structural-value gate for durable knowledge.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/keep-summarizing/detect-structural-update.md` for directive-specific behavior.

## Runtime Rules

- `ks-directive-selection`: `rules/ks-directive-selection.yaml`
- `ks-structural-value`: `rules/ks-structural-value.yaml`
- `ks-sensitivity-filter`: `rules/ks-sensitivity-filter.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/directives/keep-summarizing/index.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
