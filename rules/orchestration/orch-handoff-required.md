---
id: orch-handoff-required
applies_when:
  - a task, phase, or plan execution completes or is blocked
  - an executor-result or orchestration handoff is created after orchestration or execution work
enforcement: must
load: conditional
requires: []
---

# Orchestration Handoff Required

## Purpose

Require one compact executor-result handoff for an initial executor result before its first acceptance. After acceptance, continuation consumes the compact accepted result; acquiring, publishing, or retrying review/control facts does not rewrite or replay an executor handoff. Durable knowledge and orchestration strategy decisions stay outside executor-result handoffs.

## Must

- Require each completed or partial meaningful executor move to record a knowledge disposition of `none`, `update`, `supersede`, or `reclassify` with task-local evidence.
- Reject executor disposition text that names knowledge paths, invokes any `ks-*` skill, cites authority outside the compiled task scope, or uses paths outside that scope; final orchestration review owns approved persistence delegation.

- Run the creation-safe task projection before atomically creating/indexing an `executor-result` handoff. Creation validation must not perform harness observation, review dispatch, or acceptance.
- Create an `executor-result` handoff before reporting a task, phase, or plan execution complete or blocked.
- For a task-scoped executor-result, require explicit `related.plan` and `related.task` matching the assigned task. Missing, null, conflicting, or mismatched plan identity fails closed before `Completed`, not only before `build-review-package`; do not infer plan ownership from a local task ID.
- Default executor-result handoffs to sparse YAML. Use Markdown only when a real blocker, failure, or broad cross-repository impact needs narrative that YAML cannot express safely.
- Include only executor-owned facts needed for continuation: identity, related artifacts, result state, concise summary, changed files, validation commands and results, unresolved blockers, `task_fit_check`, repository/preflight evidence, compact CodeGraph evidence, and `delegation_evidence`. Review, receipt, publication, accepted-result, and later audit facts remain outside the handoff.
- Omit empty optional blocks, placeholder headings, duplicated spec/plan/task prose, raw chat logs, private reasoning, unrelated history, generic reminders, and non-applicable sections.
- For completed or partial task results, include `task_fit_check` naming the related task, result `clean|repaired|unresolved|skipped`, and findings only when meaningful. Check the compiled task brief and assigned task; inspect full specification, plan, and phase artifacts only when compiled context is inconsistent or a reviewer finds a source-contract problem.
- For executor-result handoffs, preserve execution safety evidence where applicable: repository preflight or accepted-baseline evidence, validation evidence, drift/gap verification, unresolved blockers, and changed-path evidence.
- For executor-result handoffs, include compact CodeGraph evidence when source-code inspection or edits were in scope. The evidence must be no larger than `root`, `applicable`, `up_to_date`, and required fallback or blocker facts unless a failure needs more detail.
- For executor-result handoffs, explicitly record no-index fallback when a target repository lacks `.codegraph/`; do not omit CodeGraph evidence silently when source-code work was in scope.
- Use `delegation_evidence` as neutral proof of mandatory task ownership. It records only delegated state, `owner_kind: subagent`, minimum agent/run identity, and provider-neutral `host-native|execution-flow` mechanism.
- For contract-decoupled task handoffs, include compact `contract_decoupling` evidence: common contract group, common contracts checked, validation scope, `peer_implementation_validation_used: false`, and forbidden peer validation result.
- For barrier participants, include compact `barrier` evidence with barrier id, participant role, readiness `reached|blocked`, and whether convergence remains pending.
- For convergence owners, include compact `barrier` and `convergence` evidence showing every participant completed or blocked with executor-result handoffs before joint validation began.
- For review handoffs or review-adjacent executor results that carry specification-included defects, include `defect_closure` evidence only as review-owned lifecycle evidence or carry-forward status; executors must not delete defect evidence.
- Do not report execution complete while drift or gaps remain within task scope. Record out-of-scope findings as unresolved issues and block completion when they prevent conformance with the assigned artifacts.
- Keep executor-result handoffs on carried spec, plan, phase, task, declared handoff, and task-scoped source or test context only; do not retrieve durable knowledge during execution-completion handoffs.
- Update `.work-bundle/orchestration/handoff/index.jsonl` with id, type, status, path, project, timestamps, and related spec, plan, phase, and task links when helper/index support is available for the handoff format.
- Mark new handoffs `lifecycle_authority: location-v1`, derive current status from `active|reviewed|superseded|archived` location, move identical bytes for actual changes, and make same-state requests write-free no-ops. Preserve unmarked legacy fallback; on its first actual transition create only the digest/type/plan/task/status override. Permit the index to retain a pre-existing duplicate identity only for unmarked, same-directory, no-override copies; reject identity-based lifecycle mutation as ambiguous. Keep new identities unique and reject every other duplicate, type, binding, digest, override, or location contradiction.
- Require phase-scoped and plan-scoped `executor-result` handoffs when those scopes complete, using the same sparse structured contract. These handoffs are execution results, not review reports.
- Treat orchestration handoffs as legacy artifacts only. Do not create new `orchestration` handoffs from the active workflow.

## Must Not

- Mark execution complete without the required handoff for the completed or blocked scope.
- Store handoffs under `.work-bundle/knowledge/`.
- Retrieve durable knowledge while creating executor-result handoffs during `execute-plan`.
- Include forbidden executor advice fields in executor-result handoffs: `suggested_durable_conclusions`, `durable_candidate_facts`, `recommended_orchestration_review`, `recommended_next_actions`, `delegation`, `deviations`, `strategy_advice`, `knowledge_persistence`, or `baseline`.
- Include `acceptance_review`, review/verdict/target/frontier/reset/receipt/publication data, accepted-result identity/time/observations, or later audit facts in a new executor-result handoff.
- Use executor-result handoffs for durable-knowledge persistence recommendations, phase/plan/spec review advice, or orchestration strategy advice.
- Omit changed files, validation evidence, unresolved blockers, or `task_fit_check` when they are applicable to the completed or partial result.
- Claim a clean result without recording the compiled brief and assigned task checked, repairs made, and recheck outcome.
- Omit applicable compact CodeGraph fallback, up-to-date, or blocker evidence from executor-result handoffs for source-code work.
- Omit neutral `delegation_evidence` from a task executor-result handoff, record a non-subagent owner, or add UI, visibility, fallback, or internal-worker fields to ownership provenance.
- Omit contract-only validation evidence from a contract-decoupled task handoff, or report peer implementation validation as used before barrier release.
- Omit barrier readiness evidence from a barrier participant handoff, or schedule convergence without participant completed/blocked handoffs.
- Skip handoff creation because subagent execution blocked or partial completion made the outcome informal.
- Create new active `handoff-orch-*` artifacts as continuation output.

## Validation

- Confirm a handoff file exists under `.work-bundle/orchestration/handoff/` before completion is reported.
- Confirm handoff type and sparse executor-result fields match the completed scope by applicability, not by fixed Markdown section presence.
- Confirm executor-result handoffs are sparse YAML by default, omit empty optional fields, and reject forbidden executor advice fields.
- Confirm executor-result handoffs created during execution did not invoke knowledge retrieval.
- Confirm executor-result handoffs identify the compiled brief and assigned task checked; include findings, repairs, and final recheck evidence; and escalate to full source artifacts when compiled context is inconsistent.
- Confirm executor-result handoffs include applicable compact CodeGraph evidence for every source-code target: root, applicability, `up_to_date`, and no-index, sync-failed, stale, or blocker facts when used.
- Confirm task executor-result handoffs include closed neutral `delegation_evidence` with delegated state, subagent owner kind, agent/run identity, and provider-neutral mechanism.
- Confirm contract-decoupled task handoffs include common-contract validation scope and `peer_implementation_validation_used: false`.
- Confirm barrier participant and convergence-owner handoffs include readiness or release evidence by applicability.
- Confirm the handoff index entry reflects the new or updated handoff.
- Confirm the complete-byte digest is stable across lifecycle changes, rebuilt lookup derives marked state from location, bounded legacy override precedence survives restart, and same-state requests change no bytes or controller records.
- Confirm no active workflow creates new orchestration handoffs.

## On Violation

For an unaccepted initial executor result, stop completion reporting and create or repair its compact executor-result handoff. For an already accepted task, use its compact accepted result and route only the affected product, publication, or finalization owner; never redispatch execution merely because a handoff is absent from post-acceptance context. Remove forbidden advice fields and fill missing initial-result evidence only within that initial handoff. If active orchestration handoff creation is attempted, reject it and use active specs, plans, phases, tasks, indexes, and compact accepted results for continuation state.
