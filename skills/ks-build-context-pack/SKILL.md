---
name: ks-build-context-pack
description: 'Build temporary agent context packs from canonical durable knowledge.'
---

# ks-build-context-pack

## Scope

Build temporary agent context packs from canonical durable knowledge.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/keep-summarizing/build-context-pack.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `rules/ks-knowledge-boundary.yaml`
- `ks-structural-value`: `rules/ks-structural-value.yaml`
- `ks-context-pack-policy`: `rules/ks-context-pack-policy.yaml`
- `ks-sensitivity-filter`: `rules/ks-sensitivity-filter.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/directives/keep-summarizing/index.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
