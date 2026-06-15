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

- `orch-directive-selection`: `rules/orchestration/orch-directive-selection.md`
- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-knowledge-gateway`: `rules/orchestration/orch-knowledge-gateway.md`
- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`
- `orch-review-completion`: `rules/orchestration/orch-review-completion.md`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Review Delegation

Determine whether validated implementation and review evidence is a structural update. For mixed implementation, validation, handoff, and review evidence, delegate knowledge maintenance to `ks-extract-valuable-points`; use `ks-breakdown-design` only for design-file-only evidence.

Provide the reviewed specification, plan, relevant handoffs, validation evidence, changed project files or symbols, expected durable conclusions, target project identity, and current disposition. After the delegated `ks-*` owner returns, validate its structural-value result, written or updated durable paths or evidence-backed no-write rationale, index rebuild status, blockers, and completion state before resuming disposition evaluation. Keep review blocked and do not archive when delegation is unavailable or its return evidence is incomplete.

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration. You may invoke, schedule, or hand off to an approved `ks-*` owner and consume its result, but do not directly create, edit, promote, delete, or index durable knowledge.
