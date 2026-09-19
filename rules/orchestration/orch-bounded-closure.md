---
id: orch-bounded-closure
applies_when:
  - orchestration admission evaluates active workspace blockers or a scoped implementation exemption
  - orchestration dispatch or reconciliation is blocked by unresolved workspace blocker evidence
enforcement: must
load: conditional
requires: []
---

# Orchestration Admission and Blocker Boundary

## Purpose

Keep ordinary orchestration mutation behind current workspace blocker authority while keeping every exemption bound to one exact blocker and flow.

## Must

- Resolve admission from the current workspace metadata authority before ordinary orchestration mutation.
- Deny ordinary dispatch or reconciliation when an active blocker has current, workspace-contained specification evidence and no matching active exemption.
- Match an implementation exemption by both the exact blocker ID and the exact authorized flow ID.
- Preserve unrelated blocker and exemption entries when retiring one scoped exemption.

## Must Not

- Do not infer admission from review history, review counts, or administrative finalization state.
- Do not treat a missing, malformed, escaping, or symlinked blocker specification as valid evidence.
- Do not broaden one blocker exemption to another blocker or flow.

## Validation

- Confirm admitted mutations have either no active blockers or an exact active blocker/flow exemption, and that denied operations name the controlling metadata and blocker evidence.

## On Violation

- Stop the affected mutation, report the controlling blocker or malformed exemption, and repair that owning metadata before retrying.
