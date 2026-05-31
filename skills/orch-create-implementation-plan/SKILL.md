---
name: orch-create-implementation-plan
description: 'Create executable implementation plans, phases, and tasks from a specification.'
---

# orch-create-implementation-plan

## Scope

Create executable implementation plans, phases, and tasks from a specification.

## Role Context

Before directive-specific work, call `wb-select-role-context` to resolve the compact role_context for the current task, lifecycle stage, and perspective. Work under the selected stable role context; do not invent an ad hoc role.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/orchestration/create-implementation-plan.md` for directive-specific behavior.

## Runtime Rules

- `orch-directive-selection`: `rules/orch-directive-selection.yaml`
- `orch-orchestration-boundary`: `rules/orch-orchestration-boundary.yaml`
- `orch-knowledge-gateway`: `rules/orch-knowledge-gateway.yaml`
- `orch-artifact-role-separation`: `rules/orch-artifact-role-separation.yaml`
- `orch-contract-loading`: `rules/orch-contract-loading.yaml`
- `orch-plan-quality`: `rules/orch-plan-quality.yaml`
- `orch-plan-open-question-gate`: `rules/orch-plan-open-question-gate.yaml`
- `orch-knowledge-update-disposition`: `rules/orch-knowledge-update-disposition.yaml`
- `orch-spec-open-question-boundary`: `rules/orch-spec-open-question-boundary.yaml`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/orchestration/contract/`

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration; do not write durable knowledge.
