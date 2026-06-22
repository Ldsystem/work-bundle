---
id: handoff-orchestration-v1
type: contract
status: legacy
artifact_type: orchestration-handoff
active_creation: false
---

# Orchestration Handoff Contract

This contract is legacy-only. It remains as compatibility documentation for existing archived or historical `handoff-orch-*` artifacts, but the active workflow must not create new orchestration handoffs.

Continuation state now comes from active specifications, plans, phases, tasks, indexes, and compact `executor-result` handoffs.

## Active Workflow Rule

- Do not create new active `handoff-orch-*` artifacts.
- Do not advertise orchestration handoffs as an active continuation feature.
- Do not require orchestration handoffs for execution, review, or archive readiness.
- Keep existing archived or historical orchestration handoffs readable and indexable during migration.

## Legacy Shape

Historical orchestration handoffs may contain narrative sections such as current objective, decisions made, implementation scope, risks, open questions, recommended next action, and related working artifacts. These sections are not an active creation template.
