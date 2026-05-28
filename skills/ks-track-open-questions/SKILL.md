---
name: ks-track-open-questions
description: 'Persist user-confirmed future-work watchpoints as accepted open questions.'
---

# ks-track-open-questions

## Scope

Persist user-confirmed future-work watchpoints as accepted open questions.

## Role Context

Before directive-specific work, call `wb-select-role-context` to resolve the compact role_context for the current task, lifecycle stage, and perspective. Work under the selected stable role context; do not invent an ad hoc role.

## Workflow Reference

Use `references/ks-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/ks-directives/track-open-questions.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `references/rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `references/rules/ks-persistence-gate.yaml`
- `ks-open-question-policy`: `references/rules/ks-open-question-policy.yaml`
- `ks-note-state-authority`: `references/rules/ks-note-state-authority.yaml`
- `ks-index-maintenance`: `references/rules/ks-index-maintenance.yaml`
- `ks-sensitivity-filter`: `references/rules/ks-sensitivity-filter.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/ks-directives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
