---
id: orch-review-completion
applies_when:
  - review-plan runs after implementation
  - orchestration completion may create or change durable implementation knowledge during specification authoring, planning, or review
enforcement: must
load: conditional
requires: []
---

# Orchestration Review Completion

## Purpose

Govern final review, knowledge-update disposition, delegate-return-resume for structural updates, and archival of completed orchestration artifacts. Durable knowledge remains clean; orchestration artifacts are derived. Review may delegate durable work but must not write durable knowledge directly.

## Must

- Run review only through `review-plan` after execution, using related active specification, plan, phase, task, handoff, and referenced project files.
- Validate that specification requirements, plan coverage, handoff evidence, project file changes, validation results, and status indexes are coherent before archival.
- Validate that executor-result handoffs contain complete and consistent CodeGraph evidence when source-code work required it: index presence, sync command/result, graph query or explored symbol, post-change sync when indexed source changed, accepted no-index or `sync-failed` fallback, and final graph impact result.
- Validate that executor-result handoffs contain complete and consistent visible delegation evidence when task, phase, or plan ownership was delegated, including `visible_reference` when available and `internal_spawn_used_for_task_delegation: false`.
- Reject completion when applicable CodeGraph or delegation evidence is missing, incomplete, stale, or contradictory to the implementation scope, target repository state, or execution mode.
- Include `Knowledge Base Update` disposition in specifications and carry disposition, expected durable conclusions, evidence sources, and follow-up path into plans, tasks, and handoff criteria.
- Collect suggested durable conclusions or explicit `none` in executor-result handoffs.
- assess validated implementation and review evidence for structural updates.
- delegate mixed structural evidence to ks-extract-valuable-points; use `ks-breakdown-design` only when structural evidence is design-file-only.
- Provide the target project identity, reviewed specification, plan, relevant handoffs, validation evidence, changed project files or symbols, expected durable conclusions, structural-update summary, and current disposition to the delegated `ks-*` owner.
- validate returned structural-value result durable paths or no-write rationale index rebuild status blockers and completion state before resuming disposition evaluation.
- Resume disposition evaluation only after delegated return evidence is complete and consistent.
- Gate review archive on disposition `completed` or `not-needed`.
- Emit a final line in this exact form: `Knowledge update disposition: completed|not-needed|blocked|required`.
- Archive related active specification, plan, phase, task, and handoff artifacts only when all review checks pass and disposition is `completed` or `not-needed`.
- Mark handoffs `reviewed`, move artifacts from `active/` to `archived/`, refresh orchestration indexes, and report archived paths on success.
- Create a repair specification on review failure instead of editing implementation source files.
- Link repair specifications to the reviewed plan, related handoffs, discrepancies, evidence, severity, required fixes, and acceptance criteria.

Disposition gate:

| Disposition | Meaning for archive |
| --- | --- |
| `completed` | Delegated return identifies written or updated durable paths and successful index rebuild status |
| `not-needed` | Delegated structural-value assessment safely concludes no durable write is warranted with evidence-backed no-write rationale |
| `required` | Structural update still pending; archive blocked |
| `blocked` | Delegation unavailable, incomplete, contradictory, or lacking actionable blocker path; archive blocked |

Delegate-return-resume protocol:

1. Set or retain `Knowledge update disposition: required` when structural update is identified.
2. Delegate to the approved `ks-*` owner with full review inputs.
3. Require return of structural-value result, durable paths or evidence-backed no-write rationale, index rebuild status, blockers, and completion state.
4. Validate the return, then resume disposition evaluation.
5. Archive only when disposition resolves to `completed` or `not-needed` and all other review checks pass.

## Must Not

- Archive during execute-plan or before review completes successfully.
- Archive completed plans while knowledge update disposition remains `required` or `blocked`.
- Directly create, edit, promote, delete, or index `.work-bundle/knowledge/**` from orchestration review work.
- Do not treat missing, incomplete, contradictory, or blocked delegation evidence as completed or not-needed.
- Do not treat missing, incomplete, contradictory, or blocked CodeGraph sync/query/post-change/fallback evidence as completed when the completed task required CodeGraph evidence.
- Do not treat missing, incomplete, contradictory, or blocked visible delegation evidence as completed when plan, phase, or task ownership was delegated.
- Create orchestration plan phases or tasks that write `.work-bundle/knowledge/` directly.
- Make execution agents browse `.work-bundle/knowledge/` directly.
- Fix implementation source files when review fails; create a repair specification instead.
- Delete archived artifacts; move them to `archived/` only.
- Ignore failed validation or missing handoff evidence and archive anyway.

## Validation

- Confirm review used only allowed context and gateway retrieval when durable knowledge was needed.
- Confirm required CodeGraph evidence is present and consistent for source-code targets before accepting completion or archival.
- Confirm required visible delegation evidence is present and consistent before accepting delegated execution completion or archival.
- Confirm structural updates followed delegate-return-resume and returned complete evidence before archive resumed.
- Confirm final disposition is one of `completed`, `not-needed`, `blocked`, or `required` with supporting evidence.
- Confirm archive occurred only on success with disposition `completed` or `not-needed`.
- Confirm failure paths produced a repair specification and reported blocked or required disposition without archival.
- Confirm indexes under `.work-bundle/orchestration/spec/`, `plan/`, and `handoff/` were refreshed after successful archive.

## On Violation

Stop review or archive, report the missing handoff, disposition, CodeGraph evidence, or delegation evidence, keep active artifacts in place, and resume only after the missing or contradictory evidence is repaired, disposition evaluation completes with valid delegated return evidence, or a repair specification path is established.
