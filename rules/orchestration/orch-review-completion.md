---
id: orch-review-completion
applies_when:
  - review-plan audits a completed or blocked implementation plan
  - orchestration artifacts may be finalized or archived
enforcement: must
load: conditional
requires: []
---

# Direct Review and Completion

## Purpose

Keep independent product review advisory, keep controller/orchestrator acceptance authoritative, and keep final workflow closure compact, factual, and non-recursive.

## Must

- Require a distinct implementation reviewer to compare the exact frozen candidate with every verified specification and plan obligation plus capable focused observations.
- Let the reviewer issue an advisory `accept`, `repair`, or `blocked` assessment with concrete findings. Green tests cannot hide missing behavior.
- Require the controller/orchestrator to assess the review advice against user purpose, accepted authority, and the product before deciding acceptance, repair, blocking, or continuation. Reviewer advice is not an automatic veto or acceptance.
- Keep missing historical records, indexes, knowledge state, and controller ceremony outside the controller/orchestrator product decision unless the product is ambiguous, unsafe, inaccessible, or impossible to review.
- Carry controller/orchestrator accepted task decisions through canonical `accepted-task-result-v1` records, preserving the exact review advice considered.
- Use one compact final audit for coverage, review advice, current tests, material defects, knowledge disposition/return, repository facts, and archive readiness; the controller/orchestrator assesses that advice and owns the final workflow decision.
- Keep finalization mechanical: canonical references, lifecycle, clean baselines, destinations, indexes, and binding release only.

## Must Not

- Do not repeat code review during final audit, reconstruct history, replay transient evidence, let helpers infer semantic sufficiency, or mechanically promote a reviewer recommendation into acceptance or rejection.

## Validation

- Confirm exact candidate identity, distinct reviewers, obligation coverage, explicit controller/orchestrator assessment, compact accepted results, and a non-recursive final audit.

## On Violation

- Report the unmet review or closure condition to the controller/orchestrator, which decides whether to accept, repair, block, or request distinct rereview.
