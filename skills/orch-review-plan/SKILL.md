---
name: orch-review-plan
description: Perform direct implementation review and compact final WorkBundle workflow review against exact verified authority and frozen candidates.
---

# Review WorkBundle Implementation and Closure

Use direct product review for implementation correctness and one compact final workflow review for closure. These are separate judgments.

## Implementation review

The reviewer must be distinct from the implementor. For a task review, compare the exact frozen commit or worktree candidate with the complete current task authority closure: its named specification requirements/decisions, applicable root/phase authority, complete task and dependencies, accepted dependency results, connected ownership/interfaces, edge/failure behavior, and claim-relevant focused observations. For an integrated review, compare the exact candidate with every planned feature and acceptance obligation in the complete plan tree. After a repair, repeat the applicable complete closure or integrated comparison against the current candidate; prior findings may guide inspection but cannot narrow review to the textual delta or carry forward acceptance. Passing tests cannot hide omitted behavior.

Issue an advisory `accept`, `repair`, or `blocked` assessment from product correctness. Missing or defective indexes, historical handoffs, knowledge state, or controller ceremony are separate supporting-state defects unless they make the actual product ambiguous, unsafe, inaccessible, or impossible to review. Store the advice and findings in the current canonical `implementation-review-v3`; its `authority_identity` binds a task review to the complete task authority closure and an integrated review to the complete plan tree. Its schema field remains named `verdict`, but it is the reviewer's recommendation, not orchestration authority. Re-review after repair updates the same active review identity; it does not preserve intermediate verdict copies.

## Accepted continuation

The controller/orchestrator assesses the exact review advice and findings against user purpose, accepted specification/plan authority, the product, and current observations. It then owns acceptance, repair routing, blocking, and continuation. When it accepts, it creates one `accepted-task-result-v2` that references the exact executor result and implementation review advice when required, plus the current task-authority identity, validation outcomes, product identity, material defects, and knowledge disposition. Repair the active record at the same identity. Consumers reuse this compact controller decision; they do not reconstruct review history.

## Final workflow review

A distinct final auditor advises on plan/task coverage, controller-accepted implementation decisions, relevant current test outcomes, unresolved material defects, knowledge disposition/return, repository finalization facts, and truthful archive readiness. Do not reread source for code quality or repeat implementation review. The controller/orchestrator assesses that advice and writes or repairs its `final-workflow-review-v1` closure decision at the same identity. Deterministic finalization validates canonical references, lifecycle state, clean baselines, archive destinations, indexes, and binding release without inventing or reinterpreting the controller decision.

## Self-check

- [ ] A task implementation verdict covers every obligation in its complete current authority closure, while an integrated verdict covers every specification and plan obligation against the exact candidate.
- [ ] A repaired candidate received a complete current-candidate review rather than delta-only inspection or inherited acceptance.
- [ ] A task review is fresh for its source-addressed authority closure; unrelated specification prose, source records, plan allocation, and phase membership did not manufacture staleness, while referenced requirements/decisions, applicable root/phase policy, task/dependency authority, accepted dependency results, or connected ownership/interfaces did.
- [ ] Active executor, review, accepted-result, and final-review repairs retained their canonical identities instead of creating revision copies.
- [ ] The reviewer is distinct, findings identify the affected requirement and product boundary, and the controller/orchestrator explicitly assessed the advice rather than obeying it automatically.
- [ ] Supporting-state defects were routed separately and did not veto otherwise correct reviewable work.
- [ ] The final workflow review is compact and does not repeat code review or reconstruct history.
- [ ] Finalization carried the controller/orchestrator decision and performed only mechanical checks and transitions.
