---
name: ks-resolve-open-question
description: 'Resolve, update, split, or keep accepted open-question watchpoints.'
---

# ks-resolve-open-question

## Scope

Resolve, update, split, or keep accepted open-question watchpoints.

## Role Context

Before directive-specific work, call `wb-select-role-context` to resolve the compact role_context for the current task, lifecycle stage, and perspective. Work under the selected stable role context; do not invent an ad hoc role.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/keep-summarizing/resolve-open-question.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `rules/ks-persistence-gate.yaml`
- `ks-open-question-policy`: `rules/ks-open-question-policy.yaml`
- `ks-note-state-authority`: `rules/ks-note-state-authority.yaml`
- `ks-index-maintenance`: `rules/ks-index-maintenance.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/directives/keep-summarizing/index.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
