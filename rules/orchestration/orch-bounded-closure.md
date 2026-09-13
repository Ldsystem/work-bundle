---
id: orch-bounded-closure
applies_when:
  - all executor attempts for an orchestration flow are terminal and post-execution integrated review is about to begin, complete, or report status
  - a post-execution orchestration flow reaches its fifth completed review round or must be administratively closed with unresolved blockers
  - orchestration dispatch or reconciliation encounters finalization-required state or an active workspace blocker
enforcement: must
load: conditional
requires: []
---

# Bounded Post-Execution Closure

## Purpose

Bound post-execution integrated review and repair without counting pre-execution specification or plan revisions, losing unresolved product truth, or duplicating the controller's mechanical state machine.

## Must

- Resolve the working workspace before applying policy. `.work-bundle/project.yaml#orchestration_control` is the portable policy and stable-state projection owner; the controller ledger under `.work-bundle/runtime/orchestration-control/` is the canonical round-history owner. Legacy workspaces may omit the policy.
- Keep each portable flow projection limited to stable flow ID, execution-complete state, latest reserved and completed round IDs, frozen target identity, outcome, and finalization state/outcome. Do not embed review history, transient handoff chains, credentials, or device-local paths.
- Treat one post-execution review round as beginning only after all executor attempts are terminal. Plan and specification revisions do not consume post-execution review rounds.
- Use `begin-review-round` before evidence preparation or reviewer dispatch. An exact request ID and target identity is idempotent; the same request with a different target identity is a different request and reserves a new round.
- Use `complete-review-round` exactly once with either a store-owned immutable review reference for `accepted|findings` or a factual controller audit-block record for a blocked attempt. A factual controller audit-block must not impersonate a product verdict. Duplicate exact completion is a no-op and conflicting completion fails closed.
- Use `review-round-status` for current counts, latest frozen target, and finalization diagnostics. Do not reconstruct round state from plan versions, review files, resumes, branches, or handoff history.
- After an accepted outcome, proceed through the normal final audit, knowledge gate, archive, and index path. When unresolved findings or a blocked attempt complete the fifth completed round, stop reconciliation and use `finalize-with-blockers`.
- Apply forced-finalization order exactly: persist finalization-required state; validate the supplied residual specification and clean portable source baselines; persist an active workspace blocker; finalize the knowledge disposition from validated review-owned return evidence; archive the origin specification and plan and update their indexes without overwriting collisions; release owned bindings; then persist terminal closure.
- Preserve incomplete administrative stages for retry. A retry may finish knowledge, archive, binding-release, or terminal-record mechanics but must not reopen product work, add a sixth round, rerun accepted evidence, or erase the active blocker.
- Apply shared admission by operation class. An exhausted flow refuses reconciliation before its blocker is written. An active workspace blocker refuses ordinary new work and other unexempted reconciliation. Read-only diagnosis, round completion, blocker recording, knowledge return, and finalization remain available so the controller can explain and finish closure.
- Limit implementation exemptions to the exact flow and blocker, and restore the exact backed-up blocker while preserving newer unrelated metadata.
- Migrate only current workspace metadata by renaming the legacy policy key to `post_execution_review_round_limit: 5`. Do not inspect, reinterpret, or rewrite historical specifications, plans, handoffs, reviews, or evidence.
- During builtin deployment, retain the project shim until builtin deployment is ready, then remove only that owned shim as part of the same bounded migration so duplicate rule IDs never enter enabled rule stores.

## Must Not

- Do not use `review_revision_limit` as current execution policy or count specification/plan edits, task reviews, reviewer retries, publication retries, resumes, or branches as post-execution rounds.
- Do not bypass admission by relabeling an operation that still dispatches execution, review, or reconciliation.
- Do not call forced blocker closure for an accepted product outcome; accepted work follows normal final audit and archive gates.
- Do not let audit-block evidence assert semantic correctness, acceptance, findings, or product rejection.
- Do not overwrite archive collisions, remove unrelated blockers or bindings, mutate historical evidence, or create a parallel recovery subsystem.

## Validation

- Inspect the controller caller, canonical ledger/state transition definitions, final-audit consumer, and representative accepted, unresolved-fifth-round, pre-blocker refusal, active-workspace-blocker, duplicate-request, different-target, and administrative-retry scenarios.
- Confirm the rule index mirrors this front matter and the observable triggers are concrete.
- Confirm current instruction owners use the four controller commands and reserve the limit for post-execution rounds only.
- Confirm forced closure preserves a residual specification, portable source baselines, active blocker evidence, validated knowledge return, archive collision safety, owned-binding release, and retryable incomplete administrative state.

## On Violation

Stop the affected dispatch, reconciliation, review, archive, or finalization step. Report the controller status and metadata/blocker evidence, then resume only the first owning mechanical or semantic stage without replaying accepted work.
