---
name: ks-write-knowledge
description: 'Write or update atomic durable knowledge notes after all persistence gates pass.'
---

# ks-write-knowledge

## Scope

Write or update atomic durable knowledge notes after all persistence gates pass.

## Workflow Reference

Use `references/ks-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/ks-directives/write-knowledge.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `references/rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `references/rules/ks-persistence-gate.yaml`
- `ks-structural-value`: `references/rules/ks-structural-value.yaml`
- `ks-perspective-routing`: `references/rules/ks-perspective-routing.yaml`
- `ks-sensitivity-filter`: `references/rules/ks-sensitivity-filter.yaml`
- `ks-index-maintenance`: `references/rules/ks-index-maintenance.yaml`
- `ks-git-authority`: `references/rules/ks-git-authority.yaml`
- `ks-note-state-authority`: `references/rules/ks-note-state-authority.yaml`
- `ks-off-switches`: `references/rules/ks-off-switches.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/ks-directives.md`
- `references/ks-perspectives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
