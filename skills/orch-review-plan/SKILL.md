---
name: orch-review-plan
description: 'Review completed implementation and archive or create repair specifications.'
---

# orch-review-plan

## Scope

Review completed implementation and archive or create repair specifications.

## Workflow Reference

Use `references/orch-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/orch-directives/review-plan.md` for directive-specific behavior.

## Runtime Rules

- `orch-directive-selection`: `references/rules/orch-directive-selection.yaml`
- `orch-orchestration-boundary`: `references/rules/orch-orchestration-boundary.yaml`
- `orch-knowledge-gateway`: `references/rules/orch-knowledge-gateway.yaml`
- `orch-artifact-role-separation`: `references/rules/orch-artifact-role-separation.yaml`
- `orch-plan-quality`: `references/rules/orch-plan-quality.yaml`
- `orch-execution-boundary`: `references/rules/orch-execution-boundary.yaml`
- `orch-handoff-required`: `references/rules/orch-handoff-required.yaml`
- `orch-review-archive`: `references/rules/orch-review-archive.yaml`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration; do not write durable knowledge.
