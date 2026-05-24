---
name: ks-resolve-open-question
description: 'Resolve, update, split, or keep accepted open-question watchpoints.'
---

# ks-resolve-open-question

## Scope

Resolve, update, split, or keep accepted open-question watchpoints.

## Workflow Reference

Use `references/ks-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/ks-directives/resolve-open-question.md` for directive-specific behavior.

## Runtime Rules

- `ks-knowledge-boundary`: `references/rules/ks-knowledge-boundary.yaml`
- `ks-persistence-gate`: `references/rules/ks-persistence-gate.yaml`
- `ks-open-question-policy`: `references/rules/ks-open-question-policy.yaml`
- `ks-index-maintenance`: `references/rules/ks-index-maintenance.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/ks-directives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
