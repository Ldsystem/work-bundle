---
name: ks-write-knowledge
description: 'Write or update atomic durable knowledge notes after all persistence gates pass.'
---

# ks-write-knowledge

## Scope

Write or update atomic durable knowledge notes after all persistence gates pass.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/keep-summarizing/write-knowledge.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `rules/ks-persistence-gate.yaml`
- `ks-structural-value`: `rules/ks-structural-value.yaml`
- `ks-perspective-routing`: `rules/ks-perspective-routing.yaml`
- `ks-sensitivity-filter`: `rules/ks-sensitivity-filter.yaml`
- `ks-index-maintenance`: `rules/ks-index-maintenance.yaml`
- `ks-git-authority`: `rules/ks-git-authority.yaml`
- `ks-note-state-authority`: `rules/ks-note-state-authority.yaml`
- `ks-off-switches`: `rules/ks-off-switches.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/directives/keep-summarizing/index.md`
- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
