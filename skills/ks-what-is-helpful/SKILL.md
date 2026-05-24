---
name: ks-what-is-helpful
description: 'Retrieve useful durable project knowledge for a concrete task without writing knowledge.'
---

# ks-what-is-helpful

## Scope

Retrieve useful durable project knowledge for a concrete task without writing knowledge.

## Workflow Reference

Use `references/ks-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/ks-directives/what-is-helpful.md` for directive-specific behavior.

## Runtime Rules

- `ks-directive-selection`: `references/rules/ks-directive-selection.yaml`
- `ks-knowledge-boundary`: `references/rules/ks-knowledge-boundary.yaml`
- `ks-context-pack-policy`: `references/rules/ks-context-pack-policy.yaml`
- `ks-open-question-policy`: `references/rules/ks-open-question-policy.yaml`
- `ks-sensitivity-filter`: `references/rules/ks-sensitivity-filter.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/ks-directives.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
