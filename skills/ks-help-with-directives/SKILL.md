---
name: ks-help-with-directives
description: 'Explain keep-summarizing directive choices and the shortest safe next action.'
---

# ks-help-with-directives

## Scope

Explain keep-summarizing directive choices and the shortest safe next action.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/keep-summarizing/help-with-directives.md` for directive-specific behavior.

## Runtime Rules

- `ks-directive-selection`: `rules/ks-directive-selection.yaml`
- `ks-off-switches`: `rules/ks-off-switches.yaml`

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/directives/keep-summarizing/index.md`

## Boundary

Write only under .work-bundle/knowledge allowed paths; redirect orchestration artifacts to orch-* skills.
