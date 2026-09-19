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

Keep implementation acceptance in direct independent product review and keep final workflow closure compact, factual, and non-recursive.

## Must

- Require a distinct implementation reviewer to compare the exact frozen candidate with every verified specification and plan obligation plus capable focused observations.
- Let the reviewer issue `accept`, `repair`, or `blocked` from product correctness. Green tests cannot hide missing behavior.
- Keep missing historical records, indexes, knowledge state, and controller ceremony outside the product verdict unless the product is ambiguous, unsafe, inaccessible, or impossible to review.
- Carry accepted task decisions through canonical `accepted-task-result-v1` records.
- Use one compact final workflow review for coverage, accepted verdicts, current tests, material defects, knowledge disposition/return, repository facts, and archive readiness.
- Keep finalization mechanical: canonical references, lifecycle, clean baselines, destinations, indexes, and binding release only.

## Must Not

- Do not repeat code review during final audit, reconstruct history, replay transient evidence, or let helpers infer semantic sufficiency.

## Validation

- Confirm exact candidate identity, distinct reviewers, obligation coverage, compact accepted results, and a non-recursive final audit.

## On Violation

- Withhold acceptance or finalization, report the unmet review or closure condition, and return the affected scope to repair and distinct rereview.
