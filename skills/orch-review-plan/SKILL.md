---
name: orch-review-plan
description: 'Review completed implementation and archive or create repair specifications.'
---

# orch-review-plan

## Scope

Review completed implementation and archive or create repair specifications.

## Role Context

Before directive-specific work, call `wb-select-role-context` to resolve the compact role_context for the current task, lifecycle stage, and perspective. Work under the selected stable role context; do not invent an ad hoc role.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/orchestration/review-plan.md` for directive-specific behavior.

## Runtime Rules

- `orch-directive-selection`: `rules/orch-directive-selection.yaml`
- `orch-orchestration-boundary`: `rules/orch-orchestration-boundary.yaml`
- `orch-knowledge-gateway`: `rules/orch-knowledge-gateway.yaml`
- `orch-artifact-role-separation`: `rules/orch-artifact-role-separation.yaml`
- `orch-plan-quality`: `rules/orch-plan-quality.yaml`
- `orch-execution-boundary`: `rules/orch-execution-boundary.yaml`
- `orch-handoff-required`: `rules/orch-handoff-required.yaml`
- `orch-knowledge-update-disposition`: `rules/orch-knowledge-update-disposition.yaml`
- `orch-review-archive`: `rules/orch-review-archive.yaml`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration; do not write durable knowledge.
