---
name: orch-review-plan
description: Perform direct implementation review and compact final WorkBundle workflow review against exact verified authority and frozen candidates.
---

# Review WorkBundle Implementation and Closure

Use direct product review for implementation correctness and one compact final workflow review for closure. These are separate judgments.

## Implementation review

The reviewer must be distinct from the implementor. Compare the exact frozen commit or worktree candidate directly with the verified specification and canonical plan. Inspect every planned feature, acceptance obligation, edge/failure behavior, and claim-relevant focused observation. Passing tests cannot hide omitted behavior.

Issue `accept`, `repair`, or `blocked` from product correctness. Missing or defective indexes, historical handoffs, knowledge state, or controller ceremony are separate supporting-state defects unless they make the actual product ambiguous, unsafe, inaccessible, or impossible to review. Store the verdict and findings in one canonical `implementation-review-v1`.

## Accepted continuation

After `accept`, the controller creates one `accepted-task-result-v1` that references the exact executor result, accepted implementation review when required, current validation outcomes, product identity, material defects, and knowledge disposition. Consumers reuse this compact decision; they do not reconstruct review history.

## Final workflow review

A distinct final auditor checks only plan/task coverage, accepted implementation verdicts, relevant current test outcomes, unresolved material defects, knowledge disposition/return, repository finalization facts, and truthful archive readiness. Do not reread source for code quality or repeat implementation review. Write one `final-workflow-review-v1`; deterministic finalization validates canonical references, lifecycle state, clean baselines, archive destinations, indexes, and binding release without inventing or reinterpreting the verdict.

## Self-check

- [ ] The implementation verdict covers every specification and plan obligation against the exact candidate.
- [ ] The reviewer is distinct and findings identify the affected requirement and product boundary.
- [ ] Supporting-state defects were routed separately and did not veto otherwise correct reviewable work.
- [ ] The final workflow review is compact and does not repeat code review or reconstruct history.
- [ ] Finalization carried the agent verdict and performed only mechanical checks and transitions.
