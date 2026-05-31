---
name: orch-doctor
description: 'Run read-only develop-rules and orchestrator workflow diagnostics.'
---

# orch-doctor

## Scope

Run read-only develop-rules and orchestrator workflow diagnostics.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/orchestration/doctor.md` for directive-specific behavior.

## Runtime Rules

- `orch-directive-selection`: `rules/orch-directive-selection.yaml`
- `orch-doctor-readonly`: `rules/orch-doctor-readonly.yaml`

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Boundary

Write generated orchestration artifacts only under .work-bundle/orchestration; do not write durable knowledge.
