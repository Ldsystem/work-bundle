---
name: ks-build-context-pack
description: 'Build temporary agent context packs from canonical durable knowledge.'
---

# ks-build-context-pack

## Scope

Build temporary agent context packs from canonical durable knowledge.

## Workflow Reference

Use `references/ks-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/ks-directives/build-context-pack.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `references/rules/ks-knowledge-boundary.yaml`
- `ks-structural-value`: `references/rules/ks-structural-value.yaml`
- `ks-context-pack-policy`: `references/rules/ks-context-pack-policy.yaml`
- `ks-sensitivity-filter`: `references/rules/ks-sensitivity-filter.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/ks-directives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
