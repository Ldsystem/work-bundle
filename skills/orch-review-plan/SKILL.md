---
name: orch-review-plan
description: Perform direct implementation review and compact final WorkBundle workflow review against exact verified authority and frozen candidates.
---

# Review WorkBundle Implementation and Closure

Use direct product review for implementation correctness and one compact final workflow review for closure. These are separate judgments.

## Implementation review

The reviewer must be distinct from the implementor. Compare the exact frozen commit or worktree candidate directly with the verified specification and canonical plan. Inspect every planned feature, acceptance obligation, edge/failure behavior, and claim-relevant focused observation. After a repair, repeat this complete product comparison against the current candidate; prior findings may guide inspection but cannot narrow it to the delta or carry forward acceptance. Passing tests cannot hide omitted behavior.

Issue an advisory `accept`, `repair`, or `blocked` assessment from product correctness. Missing or defective indexes, historical handoffs, knowledge state, or controller ceremony are separate supporting-state defects unless they make the actual product ambiguous, unsafe, inaccessible, or impossible to review. Store the advice and findings in the current canonical `implementation-review-v2`; its schema field remains named `verdict`, but it is the reviewer's recommendation, not orchestration authority. Re-review after repair updates the same active review identity; it does not preserve intermediate verdict copies.

## Accepted continuation

The controller/orchestrator assesses the exact review advice and findings against user purpose, accepted specification/plan authority, the product, and current observations. It then owns acceptance, repair routing, blocking, and continuation. When it accepts, it creates one `accepted-task-result-v1` that references the exact executor result and implementation review advice when required, plus current validation outcomes, product identity, material defects, and knowledge disposition. Repair the active record at the same identity. Consumers reuse this compact controller decision; they do not reconstruct review history.

## Final workflow review

A distinct final auditor advises on plan/task coverage, controller-accepted implementation decisions, relevant current test outcomes, unresolved material defects, knowledge disposition/return, repository finalization facts, and truthful archive readiness. Do not reread source for code quality or repeat implementation review. The controller/orchestrator assesses that advice and writes or repairs its `final-workflow-review-v1` closure decision at the same identity. Deterministic finalization validates canonical references, lifecycle state, clean baselines, archive destinations, indexes, and binding release without inventing or reinterpreting the controller decision.

## Self-check

- [ ] The implementation verdict covers every specification and plan obligation against the exact candidate.
- [ ] A repaired candidate received a complete current-candidate review rather than delta-only inspection or inherited acceptance.
- [ ] Active executor, review, accepted-result, and final-review repairs retained their canonical identities instead of creating revision copies.
- [ ] The reviewer is distinct, findings identify the affected requirement and product boundary, and the controller/orchestrator explicitly assessed the advice rather than obeying it automatically.
- [ ] Supporting-state defects were routed separately and did not veto otherwise correct reviewable work.
- [ ] The final workflow review is compact and does not repeat code review or reconstruct history.
- [ ] Finalization carried the controller/orchestrator decision and performed only mechanical checks and transitions.
