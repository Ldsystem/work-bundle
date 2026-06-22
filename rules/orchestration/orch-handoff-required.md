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

Require executor-result and orchestration handoffs before reporting execution or continuation complete. Handoffs record evidence for the next agent; suggested durable conclusions in handoffs are not persisted knowledge until an approved `ks-*` workflow persists them.

## Must

- Create an `executor-result` handoff before reporting a task, phase, or plan execution complete or blocked.
- Invoke `create-handoff` for required handoffs rather than writing ad hoc completion notes.
- Distinguish handoff types:
  - `orchestration`: planning, review, coordination, or conversation continuation;
  - `executor-result`: implementation result from an executor agent to the orchestration agent.
- Include required handoff fields: front matter and status badge, source context used, current state, completed and pending work, relevant files or artifacts, dependencies, risks, assumptions, open questions, validation or test evidence when applicable, and executable next actions with completion criteria.
- For executor-result handoffs, include assigned task, implementation summary, files or symbols changed, tests run, test results, deviations, unresolved issues, suggested durable conclusions, and recommended orchestration review.
- For executor-result handoffs, include a dedicated drift/gap verification section that names the related specification, root plan, parent phase, and task checked; records each finding and task-scoped repair; records the post-repair recheck result; and explicitly states when no drift or gap was found.
- For executor-result handoffs, include per-target CodeGraph evidence when source-code inspection or edits were in scope: repository root, target kind, preflight kind, `.codegraph/` index presence, applicability decision, pre-inspection `codegraph sync <repo-root>` command and result, graph query or explored symbol, bounded fallback reason when used, `sync-failed` evidence when sync fails, post-change sync result when indexed source changed, and final graph impact result.
- For executor-result handoffs, explicitly record no-index fallback when a target repository lacks `.codegraph/`; do not omit CodeGraph evidence silently when source-code work was in scope.
- For executor-result handoffs, include delegation evidence when a task, phase, or plan was delegated: delegated flag, delegation surface, `visible_reference` when the active environment provides one, `internal_spawn_used_for_task_delegation: false`, internal helper-worker usage if any, and fallback or blocker reason when visible delegation was unavailable or unsafe.
- Do not report execution complete while drift or gaps remain within task scope. Record out-of-scope findings as unresolved issues and block completion when they prevent conformance with the assigned artifacts.
- Keep executor-result handoffs on carried spec, plan, phase, task, declared handoff, and task-scoped source or test context only; do not retrieve durable knowledge during execution-completion handoffs.
- Update `.work-bundle/orchestration/handoff/index.jsonl` with id, type, status, path, project, timestamps, and related spec, plan, phase, and task links.
- Require phase-scoped and plan-scoped `executor-result` handoffs when those scopes complete, including completed tasks, validation evidence, deviations, blockers, and next executable phase or task.

## Must Not

- Mark execution complete without the required handoff for the completed or blocked scope.
- Store handoffs under `.work-bundle/knowledge/`.
- Present suggested durable conclusions as persisted knowledge.
- Retrieve durable knowledge while creating executor-result handoffs during `execute-plan`.
- Omit changed files or symbols, validation evidence, deviations, unresolved issues, or next action from executor-result handoffs.
- Omit explicit spec/root-plan/phase/task drift-gap verification evidence or claim a clean result without recording the artifacts checked and recheck outcome.
- Omit applicable CodeGraph sync/query/post-change/fallback evidence from executor-result handoffs for source-code work.
- Omit visible delegation evidence from executor-result handoffs when plan, phase, or task ownership was delegated, or record contradictory delegation evidence such as `internal_spawn_used_for_task_delegation: true`.
- Skip handoff creation because sub-agents, fallback mode, or partial completion made the outcome informal.

## Validation

- Confirm a handoff file exists under `.work-bundle/orchestration/handoff/` before completion is reported.
- Confirm handoff type, required sections, and executor-result fields match the completed scope.
- Confirm executor-result handoffs created during execution did not invoke knowledge retrieval.
- Confirm executor-result handoffs identify the specification, root plan, parent phase, and task checked; include findings, repairs, and final recheck evidence; and do not leave repairable task-scoped drift unresolved.
- Confirm executor-result handoffs include applicable CodeGraph evidence for every source-code target, including sync command/result, query or explored symbol, post-change sync result when indexed source changed, final graph impact result, and no-index or sync-failed fallback when used.
- Confirm executor-result handoffs include visible delegation evidence when delegation was used, including `visible_reference` when available and `internal_spawn_used_for_task_delegation: false`.
- Confirm the handoff index entry reflects the new or updated handoff.

## On Violation

Stop completion reporting, create or repair the missing handoff through `create-handoff`, add the missing CodeGraph or visible delegation evidence, update indexes and statuses from the handoff evidence, and only then resume the next executable action or review step.
