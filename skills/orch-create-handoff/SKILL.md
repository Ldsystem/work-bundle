---
name: orch-create-handoff
description: 'Create orchestration and executor-result handoffs for continuation or evidence.'
---

# orch-create-handoff

## Scope

Create orchestration and executor-result handoffs for continuation or evidence.

## Role Context

Before directive-specific work, call `wb-select-role-context` to resolve the compact role_context for the current task, lifecycle stage, and perspective. Work under the selected stable role context; do not invent an ad hoc role.

## Workflow Reference

Use `references/orch-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/orch-directives/create-handoff.md` for directive-specific behavior.

## Runtime Rules

- `orch-directive-selection`: `references/rules/orch-directive-selection.yaml`
- `orch-orchestration-boundary`: `references/rules/orch-orchestration-boundary.yaml`
- `orch-contract-loading`: `references/rules/orch-contract-loading.yaml`
- `orch-handoff-required`: `references/rules/orch-handoff-required.yaml`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Additional References

- `references/orch-contracts/`

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration; do not write durable knowledge.
