---
id: orch-review-completion
applies_when:
  - review-plan audits a completed or blocked implementation plan
  - orchestration artifacts may be finalized or archived
enforcement: must
load: conditional
requires: []
---

# Orchestration Review Completion

## Purpose

Keep final review focused on whether the WorkBundle workflow completed correctly. Task-scoped implementation quality belongs to independent task review before a task becomes complete.

## Must

- Confirm each required task review compared the accepted Truth Basis, implementation, test oracle, and task-local knowledge disposition before accepting the task.
- Keep approved `ks-*` persistence delegation review-owned; executor disposition evidence never authorizes knowledge retrieval or writes.

- Audit spec, plan, phase, task, handoff, and accepted task-review status coherence.
- Require fresh planned validation evidence and an `accept` task-review verdict wherever review is required.
- Verify declared dependency, barrier, and convergence gates from recorded evidence.
- Route missing handoff, status, validation, or review evidence to `review-blocked` and resume the owning execution step.
- Route incomplete durable knowledge work to `knowledge-blocked` and resume the approved `ks-*` delegate-return path.
- Route incomplete repository metadata, index, workspace, or archive mechanics to `repository-blocked` or `workspace-blocked` and use bounded deterministic helpers.
- Require specification Knowledge Base Update disposition `completed` or `not-needed` before archive.
- Create or require plan repair only for a decomposition defect, and specification repair only for a requirement, design, or authority defect.
- Complete allowed commit, applicable CodeGraph sync, metadata update, archive, and index refresh only after all gates allow finalization.

## Must Not

- Do not broadly inspect project source to redo task code review.
- Do not repair implementation or test code during final review.
- Do not substitute project-file inspection for accepted task-review evidence.
- Do not create a repair specification for every failed review gate.
- Do not archive while required knowledge, validation, review, repository, or workspace evidence is unresolved.
- Do not directly write durable knowledge from orchestration.

## Validation

- Confirm every completed review-required task has fresh validation, a valid executor-result handoff, and `accept` review evidence.
- Confirm blocker routing names the owning resume path instead of restarting the lifecycle.
- Confirm finalization and archive occur only after knowledge disposition and deterministic gates resolve.

## On Violation

Stop finalization, emit the smallest typed blocker, and resume the step that owns the missing or contradictory evidence. Repair a plan or specification only when the defect belongs to that artifact.
