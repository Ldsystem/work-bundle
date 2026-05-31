---
name: ks-maintain-indexes
description: 'Rebuild derived keep-summarizing indexes after durable knowledge changes.'
---

# ks-maintain-indexes

## Scope

Rebuild derived keep-summarizing indexes after durable knowledge changes.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/keep-summarizing/maintain-indexes.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `rules/ks-knowledge-boundary.yaml`
- `ks-index-maintenance`: `rules/ks-index-maintenance.yaml`
- `ks-git-authority`: `rules/ks-git-authority.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/directives/keep-summarizing/index.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
