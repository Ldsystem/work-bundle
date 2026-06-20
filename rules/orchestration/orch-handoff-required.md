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
- Skip handoff creation because sub-agents, fallback mode, or partial completion made the outcome informal.

## Validation

- Confirm a handoff file exists under `.work-bundle/orchestration/handoff/` before completion is reported.
- Confirm handoff type, required sections, and executor-result fields match the completed scope.
- Confirm executor-result handoffs created during execution did not invoke knowledge retrieval.
- Confirm executor-result handoffs identify the specification, root plan, parent phase, and task checked; include findings, repairs, and final recheck evidence; and do not leave repairable task-scoped drift unresolved.
- Confirm the handoff index entry reflects the new or updated handoff.

## On Violation

Stop completion reporting, create the missing handoff through `create-handoff`, update indexes and statuses from the handoff evidence, and only then resume the next executable action or review step.
