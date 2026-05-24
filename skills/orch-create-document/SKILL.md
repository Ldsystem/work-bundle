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

Use `references/orch-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/orch-directives/create-document.md` for directive-specific behavior.

## Runtime Rules

- `orch-directive-selection`: `references/rules/orch-directive-selection.yaml`
- `orch-orchestration-boundary`: `references/rules/orch-orchestration-boundary.yaml`
- `orch-knowledge-gateway`: `references/rules/orch-knowledge-gateway.yaml`
- `orch-contract-loading`: `references/rules/orch-contract-loading.yaml`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Additional References

- `references/orch-contracts/`

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration; do not write durable knowledge.
