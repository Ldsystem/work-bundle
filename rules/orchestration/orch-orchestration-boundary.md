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
- Treat canonical artifacts as authority and indexes as disposable projections.
- Use executor results for facts, implementation reviews for product verdicts, accepted task results for dependency continuation, and final workflow reviews for compact closure judgment.
- Validate structural mechanics before mutation and keep post-write checks lightweight.

## Must Not

- Do not merge artifact roles, reconstruct authority from history, create compatibility sidecars, or let structural helpers decide correctness or acceptance.
- Do not read, migrate, or rewrite historical orchestration artifacts during current-path work.

## Validation

- Confirm each artifact is schema-owned, canonically located, correctly bound, and consumed only for its stated role.

## On Violation

- Stop the affected write or consumption, route it to the canonical artifact owner, and correct the role, binding, or location before continuing.
