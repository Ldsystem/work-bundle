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

Require compact executor-result handoffs before reporting execution complete or blocked. Handoffs record only continuation and review evidence for the next agent; durable knowledge and orchestration strategy decisions stay outside executor-result handoffs.

## Must

- Create an `executor-result` handoff before reporting a task, phase, or plan execution complete or blocked.
- Default executor-result handoffs to sparse YAML. Use Markdown only when a real blocker, failure, or broad cross-repository impact needs narrative that YAML cannot express safely.
- Include only applicable executor-result fields needed for continuation or review: identity, related artifacts, result state, concise summary, changed files, validation commands and results, unresolved blockers, `task_fit_check`, repository/preflight evidence, compact CodeGraph evidence, and `delegation_evidence`.
- Omit empty optional blocks, placeholder headings, duplicated spec/plan/task prose, raw chat logs, private reasoning, unrelated history, generic reminders, and non-applicable sections.
- For completed or partial task results, include `task_fit_check` naming the related task, result `clean|repaired|unresolved|skipped`, and findings only when meaningful. The check must cover the related specification, root plan, parent phase, and assigned task.
- For executor-result handoffs, preserve execution safety evidence where applicable: repository preflight or accepted-baseline evidence, validation evidence, drift/gap verification, unresolved blockers, and changed-path evidence.
- For executor-result handoffs, include compact CodeGraph evidence when source-code inspection or edits were in scope. The evidence must be no larger than `root`, `applicable`, `up_to_date`, and required fallback or blocker facts unless a failure needs more detail.
- For executor-result handoffs, explicitly record no-index fallback when a target repository lacks `.codegraph/`; do not omit CodeGraph evidence silently when source-code work was in scope.
- Use `delegation_evidence` only as proof of task ownership delegation when applicable. It records delegated flag, visible surface, `visible_reference` when available, `internal_spawn_used_for_task_delegation: false`, internal helper-worker usage if any, and fallback or blocker reason when visible delegation was unavailable or unsafe.
- For contract-decoupled task handoffs, include compact `contract_decoupling` evidence: common contract group, common contracts checked, validation scope, `peer_implementation_validation_used: false`, and forbidden peer validation result.
- For barrier participants, include compact `barrier` evidence with barrier id, participant role, readiness `reached|blocked`, and whether convergence remains pending.
- For convergence owners, include compact `barrier` and `convergence` evidence showing every participant completed or blocked with executor-result handoffs before joint validation began.
- For review handoffs or review-adjacent executor results that carry specification-included violations, include `violation_closure` evidence only as review-owned lifecycle evidence or carry-forward status; executors must not delete violation evidence.
- Do not report execution complete while drift or gaps remain within task scope. Record out-of-scope findings as unresolved issues and block completion when they prevent conformance with the assigned artifacts.
- Keep executor-result handoffs on carried spec, plan, phase, task, declared handoff, and task-scoped source or test context only; do not retrieve durable knowledge during execution-completion handoffs.
- Update `.work-bundle/orchestration/handoff/index.jsonl` with id, type, status, path, project, timestamps, and related spec, plan, phase, and task links when helper/index support is available for the handoff format.
- Require phase-scoped and plan-scoped `executor-result` handoffs when those scopes complete, using the same sparse structured contract. These handoffs are execution results, not review reports.
- Treat orchestration handoffs as legacy artifacts only. Do not create new `orchestration` handoffs from the active workflow.

## Must Not

- Mark execution complete without the required handoff for the completed or blocked scope.
- Store handoffs under `.work-bundle/knowledge/`.
- Retrieve durable knowledge while creating executor-result handoffs during `execute-plan`.
- Include forbidden executor advice fields in executor-result handoffs: `suggested_durable_conclusions`, `durable_candidate_facts`, `recommended_orchestration_review`, `recommended_next_actions`, `delegation`, `deviations`, `strategy_advice`, or `knowledge_persistence`.
- Use executor-result handoffs for durable-knowledge persistence recommendations, phase/plan/spec review advice, or orchestration strategy advice.
- Omit changed files, validation evidence, unresolved blockers, or `task_fit_check` when they are applicable to the completed or partial result.
- Omit explicit spec/root-plan/phase/task drift-gap verification evidence or claim a clean result without recording the artifacts checked and recheck outcome.
- Omit applicable compact CodeGraph fallback, up-to-date, or blocker evidence from executor-result handoffs for source-code work.
- Omit visible `delegation_evidence` from executor-result handoffs when plan, phase, or task ownership was delegated, or record contradictory delegation evidence such as `internal_spawn_used_for_task_delegation: true`.
- Omit contract-only validation evidence from a contract-decoupled task handoff, or report peer implementation validation as used before barrier release.
- Omit barrier readiness evidence from a barrier participant handoff, or schedule convergence without participant completed/blocked handoffs.
- Skip handoff creation because sub-agents, fallback mode, or partial completion made the outcome informal.
- Create new active `handoff-orch-*` artifacts as continuation output.

## Validation

- Confirm a handoff file exists under `.work-bundle/orchestration/handoff/` before completion is reported.
- Confirm handoff type and sparse executor-result fields match the completed scope by applicability, not by fixed Markdown section presence.
- Confirm executor-result handoffs are sparse YAML by default, omit empty optional fields, and reject forbidden executor advice fields.
- Confirm executor-result handoffs created during execution did not invoke knowledge retrieval.
- Confirm executor-result handoffs identify the specification, root plan, parent phase, and task checked; include findings, repairs, and final recheck evidence; and do not leave repairable task-scoped drift unresolved.
- Confirm executor-result handoffs include applicable compact CodeGraph evidence for every source-code target: root, applicability, `up_to_date`, and no-index, sync-failed, stale, or blocker facts when used.
- Confirm executor-result handoffs include `delegation_evidence` when delegation was used, including `visible_reference` when available and `internal_spawn_used_for_task_delegation: false`.
- Confirm contract-decoupled task handoffs include common-contract validation scope and `peer_implementation_validation_used: false`.
- Confirm barrier participant and convergence-owner handoffs include readiness or release evidence by applicability.
- Confirm the handoff index entry reflects the new or updated handoff.
- Confirm no active workflow creates new orchestration handoffs.

## On Violation

Stop completion reporting, create or repair the missing compact executor-result handoff, remove forbidden advice fields, add missing task-fit, CodeGraph, repository, validation, contract-decoupling, barrier, convergence, violation-closure, or `delegation_evidence`, update indexes and statuses from the handoff evidence when supported, and only then resume the next executable action or review step. If active orchestration handoff creation is attempted, reject it and use active specs, plans, phases, tasks, indexes, and executor-result handoffs for continuation state.
