---
name: orch-create-specification
description: 'Create AI-ready implementation specifications under orchestration spec roots.'
---

# orch-create-specification

## Scope

Create AI-ready implementation specifications under orchestration spec roots.

## Role Context

Before directive-specific work, call `wb-select-role-context` to resolve the compact role_context for the current task, lifecycle stage, and perspective. Work under the selected stable role context; do not invent an ad hoc role.

## Workflow Reference

Use `references/orch-workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/orch-directives/create-specification.md` for directive-specific behavior.

## Runtime Rules

- `orch-directive-selection`: `references/rules/orch-directive-selection.yaml`
- `orch-orchestration-boundary`: `references/rules/orch-orchestration-boundary.yaml`
- `orch-knowledge-gateway`: `references/rules/orch-knowledge-gateway.yaml`
- `orch-artifact-role-separation`: `references/rules/orch-artifact-role-separation.yaml`
- `orch-contract-loading`: `references/rules/orch-contract-loading.yaml`
- `orch-spec-open-question-boundary`: `references/rules/orch-spec-open-question-boundary.yaml`
- `ks-note-state-authority`: `references/rules/ks-note-state-authority.yaml`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Additional References

- `references/orch-contracts/`

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration; do not write durable knowledge.
