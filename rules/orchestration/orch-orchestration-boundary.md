---
id: orch-orchestration-boundary
applies_when:
  - any orchestration artifact is created, updated, validated, or reviewed
  - an orch-* skill writes or validates content under .work-bundle/orchestration/
enforcement: must
load: conditional
requires: []
---

# Orchestration Platform Boundary

## Purpose

Keep every current orchestration artifact in its canonical role and keep structural mechanics separate from semantic judgment.

## Must

- Keep specifications, plans, tasks, executor results, implementation reviews, accepted task results, and final workflow reviews in their catalog-owned roles under `.work-bundle/orchestration/`.
- Keep durable knowledge under `.work-bundle/knowledge/` and delegate approved writes to `ks-*` owners.
- Treat each canonical artifact as authority only for its declared role and indexes as disposable projections.
- Use executor results for facts, implementation reviews for independent advisory findings, accepted task results for controller/orchestrator acceptance and dependency continuation, and final workflow reviews for the controller/orchestrator's compact closure decision after considering final-audit advice.
- Keep the controller/orchestrator authoritative for scope, delegation, repair routing, continuation, acceptance, re-entry, and any explicitly user-authorized delivery action. A reviewer reports advice to that owner and does not direct workers, expand scope, deliver changes, or issue the controlling decision.
- Validate structural mechanics before mutation and keep post-write checks lightweight.

## Must Not

- Do not merge artifact roles, reconstruct authority from history, create compatibility sidecars, let structural helpers decide correctness or acceptance, treat reviewer advice as an automatic acceptance/rejection command, or act on reviewer-proposed scope expansion without controller/orchestrator assessment and any required user decision.
- Do not read, migrate, or rewrite historical orchestration artifacts during current-path work.

## Validation

- Confirm each artifact is schema-owned, canonically located, correctly bound, and consumed only for its stated role; confirm reviewer advice returns to the controller/orchestrator for an explicit scope, repair, continuation, or acceptance decision.

## On Violation

- Stop the affected write or consumption, route it to the canonical artifact owner, and correct the role, binding, or location before continuing.
