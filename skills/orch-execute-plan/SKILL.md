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

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/orchestration/execute-plan.md` for directive-specific behavior.

## Runtime Rules

- `orch-directive-selection`: `rules/orchestration/orch-directive-selection.md`
- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-execute-plan`: `rules/orchestration/orch-execute-plan.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration; do not write durable knowledge.
