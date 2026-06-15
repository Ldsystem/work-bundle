---
name: orch-create-document
description: 'Create reader-facing orchestration documents from accepted context.'
---

# orch-create-document

## Scope

Create reader-facing orchestration documents from accepted context.

## Role Context

Before directive-specific work, call `wb-select-role-context` to resolve the compact role_context for the current task, lifecycle stage, and perspective. Work under the selected stable role context; do not invent an ad hoc role.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/orchestration/create-document.md` for directive-specific behavior.

## Runtime Rules

- `orch-directive-selection`: `rules/orchestration/orch-directive-selection.md`
- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-knowledge-gateway`: `rules/orchestration/orch-knowledge-gateway.md`
- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/orchestration/contract/`

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration; do not write durable knowledge.
