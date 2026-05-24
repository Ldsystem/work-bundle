---
name: orch-execute-plan
description: 'Execute implementation plans through scheduler delegation or single-agent fallback.'
---

# orch-execute-plan

## Scope

Execute implementation plans through scheduler delegation or single-agent fallback.

## Role Context

Before directive-specific work, call `wb-select-role-context` to resolve the compact role_context for the current task, lifecycle stage, and perspective. Work under the selected stable role context; do not invent an ad hoc role.

## Workflow Reference

Use `references/orch-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/orch-directives/execute-plan.md` for directive-specific behavior.

## Runtime Rules

- `orch-directive-selection`: `references/rules/orch-directive-selection.yaml`
- `orch-orchestration-boundary`: `references/rules/orch-orchestration-boundary.yaml`
- `orch-artifact-role-separation`: `references/rules/orch-artifact-role-separation.yaml`
- `orch-execution-boundary`: `references/rules/orch-execution-boundary.yaml`
- `orch-handoff-required`: `references/rules/orch-handoff-required.yaml`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration; do not write durable knowledge.
