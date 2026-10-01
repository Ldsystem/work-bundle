---
name: orch-review-plan
description: Review a frozen task or integrated implementation, record controller acceptance after advisory review, or perform final workflow closure against verified authority. Reviewers advise; controllers own acceptance.
---

# Review WorkBundle Implementation and Closure

Use direct product review for implementation correctness and one compact final workflow review for closure. These are separate judgments.

Apply `orch-artifact-authoring` to every current review/acceptance/closure record: supply semantic input to `scripts/orch.py write-implementation-review`, `scripts/orch.py write-accepted-task-result`, or `scripts/orch.py write-final-workflow-review` in the responsible role. Do not directly create or edit canonical YAML/Markdown under `.work-bundle/orchestration/`, including bootstrap repair. Malformed-active repair uses the same family writer; target-affecting conflicts remain prewrite refusals. Report applied-target and `index_effect: stale` sibling diagnostics separately; each sibling is repaired through its own family writer before the existing family index rebuild. No command success or stale projection issues the semantic decision.

## Implementation review

Build the exact target through `build-implementation-review-candidate`: commit mode uses `--candidate-commit`, worktree mode uses `--base-commit`. The stored `target.base_commit` field is unchanged. Use the current result/review ID conventions from the shared workflow; optional scaffolds provide editable payload/context rather than review meaning or acceptance.

The reviewer must be distinct from the implementor. For a task review, compare the exact frozen commit or worktree candidate with the complete current task authority closure: its named specification requirements/decisions, applicable root/phase authority, complete task and dependencies, accepted dependency results, connected ownership/interfaces, edge/failure behavior, and claim-relevant focused observations. For an integrated review, compare the exact candidate with every planned feature and acceptance obligation in the complete plan tree. After a repair, repeat the applicable complete closure or integrated comparison against the current candidate; prior findings may guide inspection but cannot narrow review to the textual delta or carry forward acceptance. Passing tests cannot hide omitted behavior.

Issue an advisory `accept`, `repair`, or `blocked` assessment from product correctness. Missing or defective indexes, historical handoffs, knowledge state, or controller ceremony are separate supporting-state defects unless they make the actual product ambiguous, unsafe, inaccessible, or impossible to review. Store the advice and findings in the current canonical `implementation-review-v3`; its `authority_identity` binds a task review to the complete task authority closure and an integrated review to the complete plan tree. Its schema field remains named `verdict`, but it is the reviewer's recommendation, not orchestration authority. Re-review after repair updates the same active review identity; it does not preserve intermediate verdict copies.

## Accepted continuation

The controller/orchestrator assesses the exact review advice and findings against user purpose, accepted specification/plan authority, the product, and current observations. It then owns acceptance, repair routing, blocking, and continuation. When it accepts, it creates one `accepted-task-result-v2` that references the exact executor result and implementation review advice when required, plus the current task-authority identity, validation outcomes, product identity, material defects, and knowledge disposition. Repair the active record at the same identity. Consumers reuse this compact controller decision; they do not reconstruct review history.

## Final workflow review

For delivery-task acceptance, mechanical prewrite checks require every other phase task's current accepted result, the current factual executor result, exact published bundle/product/manifest/bridge identities, required bridge observations, and a complete passing catalog report. The controller still judges phase purpose and completion criteria after considering required review advice. Its existing accepted-task-result is the sole continuation decision. Surface the accepted snapshot asynchronously; later findings reopen only their affected authority closure, preserving unrelated current acceptance and exact reusable observations.

A distinct final auditor advises on plan/task coverage, controller-accepted implementation decisions, relevant current test outcomes, unresolved material defects, knowledge disposition/return, repository finalization facts, and truthful archive readiness. Do not reread source for code quality or repeat implementation review. The controller/orchestrator assesses that advice and writes or repairs its `final-workflow-review-v1` closure decision at the same identity. Deterministic finalization validates canonical references, lifecycle state, clean baselines, archive destinations, indexes, and binding release without inventing or reinterpreting the controller decision.

Finalization preflights all accepted bundle cleanup targets read-only before deletion, refuses missing/mismatched payloads and live or uncertain leases, and uses the exact release owner. Dead-runner recovery still requires verified bounded child/external cleanup. Retain identity-bound cleaning/cleaned state through partial failures, resume exact current active/archived references on retry, archive only after every bundle is cleaned, then remove temporary states/root. Explicit earlier release must have matching cleaned state; failed preacceptance candidates may be explicitly released by persisted materialization identity and rematerialized without fabricated acceptance.

## Self-check

- [ ] Actual creation/active repair used the respective canonical `write-implementation-review`, `write-accepted-task-result`, or `write-final-workflow-review` command; no direct canonical or bootstrap edit occurred.
- [ ] Target-affecting refusals and applied-target/stale-sibling observations are reported separately with writer-based sibling repair.
- [ ] A task implementation verdict covers every obligation in its complete current authority closure, while an integrated verdict covers every specification and plan obligation against the exact candidate.
- [ ] A repaired candidate received a complete current-candidate review rather than delta-only inspection or inherited acceptance.
- [ ] A task review is fresh for its source-addressed authority closure; unrelated specification prose, source records, plan allocation, and phase membership did not manufacture staleness, while referenced requirements/decisions, applicable root/phase policy, task/dependency authority, accepted dependency results, or connected ownership/interfaces did.
- [ ] Active executor, review, accepted-result, and final-review repairs retained their canonical identities instead of creating revision copies.
- [ ] The reviewer is distinct, findings identify the affected requirement and product boundary, and the controller/orchestrator explicitly assessed the advice rather than obeying it automatically.
- [ ] Supporting-state defects were routed separately and did not veto otherwise correct reviewable work.
- [ ] The final workflow review is compact and does not repeat code review or reconstruct history.
- [ ] Finalization carried the controller/orchestrator decision and performed only mechanical checks and transitions.
