
---
id: handoff-exec-YYYYMMDD-001
type: executor-result
status: active
project: <project-slug>
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
source_agent: executor
target_agent: orchestration-agent
related_spec: <spec-id-or-null>
related_plan: <plan-id-or-null>
related_phase: <phase-id-or-null>
related_task: <task-id-or-null>
related_artifacts:
  - .work-bundle/orchestration/spec/active/...
  - .work-bundle/orchestration/plan/active/...
source_knowledge:
  - .work-bundle/knowledge/notes/...
changed_files:
  - <exact-file-path>
test_status: not_run|passed|failed|partial
handoff_scope: plan|phase|task|multi-task|review
---

# Executor Result Handoff: <Task / Phase / Plan Name>

![Status: active](https://img.shields.io/badge/status-active-yellow)

## 1. Handoff Summary

- **HANDOFF-ID**: handoff-exec-YYYYMMDD-001
- **Scope**: plan|phase|task|multi-task|review
- **Related Spec**: `<spec-id-or-null>` / `.work-bundle/orchestration/spec/active/...`
- **Related Plan**: `<plan-id-or-null>` / `.work-bundle/orchestration/plan/active/...`
- **Related Phase**: `<phase-id-or-null>` / `.work-bundle/orchestration/plan/active/<plan-id>/phase-xxx-<slug>.md`
- **Related Task**: `<task-id-or-null>` / `.work-bundle/orchestration/plan/active/<plan-id>/<phase-dir>/task-xxx-<slug>.md`
- **Executor**: `<executor-agent-name-or-model>`
- **Target Reviewer**: orchestration-agent
- **Execution Result**: completed|partially-completed|blocked|failed

## 2. Task Assigned

Describe the exact assignment received by the executor.

| ID | Type | Path | Status Before Execution | Status After Execution |
|---|---|---|---|---|
| SPEC-001 | specification | `.work-bundle/orchestration/spec/active/...` | active|draft|reviewed | active|implemented|reviewed |
| PLAN-001 | plan | `.work-bundle/orchestration/plan/active/...` | Planned|In progress | In progress|Completed|On Hold |
| PHASE-001 | phase | `.work-bundle/orchestration/plan/active/<plan-id>/phase-xxx-<slug>.md` | Planned|In progress | Completed|On Hold |
| TASK-001 | task | `.work-bundle/orchestration/plan/active/<plan-id>/<phase-dir>/task-xxx-<slug>.md` | Planned|In progress | Completed|On Hold |

## 3. Source Context Used

List all project knowledge, specs, plans, phase files, task files, and source files used during execution.

| ID | Type | Path | How It Was Used |
|---|---|---|---|
| KNOW-001 | knowledge | `.work-bundle/knowledge/notes/...` | [Accepted knowledge applied during implementation.] |
| SPEC-001 | specification | `.work-bundle/orchestration/spec/active/...` | [Specification section followed.] |
| PLAN-001 | plan | `.work-bundle/orchestration/plan/active/...` | [Plan section followed.] |
| PHASE-001 | phase | `.work-bundle/orchestration/plan/active/...` | [Phase section followed.] |
| TASK-001 | task | `.work-bundle/orchestration/plan/active/...` | [Task section followed.] |
| SRC-001 | source-file | `[exact source file path]` | [Source file read or modified.] |

## 4. Implementation Summary

Summarize what was implemented in deterministic terms.

- **IMPL-001**: [Concrete implemented behavior or change.]
- **IMPL-002**: [Concrete implemented behavior or change.]
- **IMPL-003**: [Concrete implemented behavior or change.]

## 5. Requirements & Constraints Validation

Report how the implementation satisfies or fails each relevant requirement and constraint from the related spec, plan, phase, and task files.

| ID | Source | Requirement / Constraint | Result | Evidence |
|---|---|---|---|---|
| REQ-001 | spec|plan|phase|task | [Requirement.] | satisfied|not-satisfied|not-applicable | [Evidence path, test, or explanation.] |
| CON-001 | spec|plan|phase|task | [Constraint.] | satisfied|not-satisfied|not-applicable | [Evidence path, test, or explanation.] |
| PAT-001 | knowledge|plan|phase|task | [Pattern/rule.] | satisfied|not-satisfied|not-applicable | [Evidence path, test, or explanation.] |

## 6. Files Changed

List every changed file. Use exact project-relative paths.

| ID | Path | Operation | Summary | Related Task |
|---|---|---|---|---|
| FILE-001 | `[exact file path]` | created|updated|deleted|renamed | [Concrete change summary.] | task-001 |
| FILE-002 | `[exact file path]` | created|updated|deleted|renamed | [Concrete change summary.] | task-002 |

## 7. Symbols Changed

List changed classes, functions, modules, interfaces, schemas, configuration keys, commands, endpoints, events, or data structures.

| ID | File | Symbol Type | Symbol Name | Change |
|---|---|---|---|---|
| SYM-001 | `[exact file path]` | class|function|module|interface|schema|config|endpoint|event|command | `[symbol name]` | [Concrete change.] |
| SYM-002 | `[exact file path]` | class|function|module|interface|schema|config|endpoint|event|command | `[symbol name]` | [Concrete change.] |

## 8. Data Model / Domain Model Impact

Use this section when the implementation affects data structures, schemas, entities, state, identifiers, domain concepts, or lifecycle behavior.

| ID | Model Type | Target | Change | Compatibility Impact |
|---|---|---|---|---|
| DATA-001 | data-model | `[entity/table/schema/state]` | [Concrete change.] | none|backward-compatible|breaking|unknown |
| DOMAIN-001 | domain-model | `[domain concept]` | [Concrete change.] | none|backward-compatible|breaking|unknown |

## 9. API / Interface / Integration Impact

Use this section when the implementation affects APIs, DTOs, events, commands, external systems, or integration behavior.

| ID | Interface Type | Target | Change | Compatibility Impact |
|---|---|---|---|---|
| API-001 | api|dto|event|command|integration | `[endpoint/interface/event/system]` | [Concrete change.] | none|backward-compatible|breaking|unknown |
| INT-001 | api|dto|event|command|integration | `[endpoint/interface/event/system]` | [Concrete change.] | none|backward-compatible|breaking|unknown |

## 10. Behavior Changed

Describe observable behavior changes.

- **BEHAVIOR-001**: [Before behavior.] → [After behavior.]
- **BEHAVIOR-002**: [Before behavior.] → [After behavior.]

## 11. Tests Run

List every test, command, manual verification, or inspection performed.

| ID | Test Type | Target | Command / Method | Result | Evidence |
|---|---|---|---|---|---|
| TEST-001 | unit|integration|e2e|manual|inspection|build | `[target]` | `[command or method]` | passed|failed|skipped|not-run | [Output, path, or summary.] |
| TEST-002 | unit|integration|e2e|manual|inspection|build | `[target]` | `[command or method]` | passed|failed|skipped|not-run | [Output, path, or summary.] |

## 12. Test Results Summary

- **TEST-STATUS**: not_run|passed|failed|partial
- **Passed**: [number]
- **Failed**: [number]
- **Skipped**: [number]
- **Not Run**: [number]
- **Failure Summary**: [Concrete failure summary or `none`.]

## 13. Deviations From Spec / Plan / Phase / Task

List every deviation from the related orchestration artifacts.

| ID | Source Artifact | Expected Instruction | Actual Implementation | Reason | Requires Review |
|---|---|---|---|---|---|
| DEV-001 | spec|plan|phase|task | [Expected instruction.] | [Actual implementation.] | [Reason.] | true|false |
| DEV-002 | spec|plan|phase|task | [Expected instruction.] | [Actual implementation.] | [Reason.] | true|false |

## 14. Problems Encountered

List execution problems encountered during implementation.

- **PROB-001**: [Problem.]
  - **Impact**: [Impact.]
  - **Action Taken**: [Action taken.]
  - **Remaining Work**: [Remaining work or `none`.]

## 15. Unresolved Issues

List unresolved issues that block completion, review, testing, or durable knowledge extraction.

- **ISSUE-001**: [Unresolved issue.]
  - **Blocks**: [spec|plan|phase|task|test|review|knowledge-update]
  - **Required Action**: [Concrete required action.]
  - **Owner**: orchestration-agent|executor|human|unknown

## 16. Open Questions

List open questions discovered during execution.

- **OQ-001**: [Question.]
  - **Required Decision**: [Specific decision needed.]
  - **Blocks**: [spec|plan|phase|task|test|review|knowledge-update]
  - **Suggested Default**: [Default if safe, otherwise `none`.]

## 17. Completion Criteria Evidence

Report evidence for completion criteria from the related plan, phase, and task files.

| ID | Source | Completion Criterion | Result | Evidence |
|---|---|---|---|---|
| DONE-001 | plan|phase|task | [Criterion.] | achieved|not-achieved|not-applicable | [Evidence.] |
| DONE-002 | plan|phase|task | [Criterion.] | achieved|not-achieved|not-applicable | [Evidence.] |

## 18. Suggested Durable Conclusions

List only conclusions that may be worth extracting into `.work-bundle/knowledge/` by `keep-summarizing`. Do not write durable knowledge directly from this handoff.

- **DURABLE-001**: [Potential durable conclusion.]
  - **Suggested Perspective**: architecture|process-flow|data-flow|data-model|domain-model|api-contract|integration|code-structure|coding-rules|testing-quality|deployment-ops|decisions|patterns|glossary
  - **Evidence**: [Changed file, test, decision, or implementation result.]
  - **Confidence**: high|medium|low
- **DURABLE-002**: [Potential durable conclusion.]
  - **Suggested Perspective**: architecture|process-flow|data-flow|data-model|domain-model|api-contract|integration|code-structure|coding-rules|testing-quality|deployment-ops|decisions|patterns|glossary
  - **Evidence**: [Changed file, test, decision, or implementation result.]
  - **Confidence**: high|medium|low

## 19. Recommended Orchestration Review

Specify what the orchestration agent should do next.

- **REVIEW-001**: [Review changed files against related spec/plan/phase/task.]
- **REVIEW-002**: [Verify tests and completion criteria.]
- **REVIEW-003**: [Resolve listed deviations, issues, or open questions.]
- **REVIEW-004**: [Decide whether to call `keep-summarizing` for durable conclusion extraction.]

## 20. Recommended Next Actions

List deterministic next actions.

| ID | Action | Owner | Depends On | Expected Output |
|---|---|---|---|---|
| NEXT-001 | [Concrete next action.] | orchestration-agent|executor|human | [dependency id or `none`] | [Expected output.] |
| NEXT-002 | [Concrete next action.] | orchestration-agent|executor|human | [dependency id or `none`] | [Expected output.] |

## 21. Handoff Completion Criteria

- **HANDOFF-DONE-001**: All changed files are listed with exact paths.
- **HANDOFF-DONE-002**: All tests run or skipped are reported with results.
- **HANDOFF-DONE-003**: All deviations from spec, plan, phase, or task files are listed.
- **HANDOFF-DONE-004**: All unresolved issues and open questions are listed.
- **HANDOFF-DONE-005**: Suggested durable conclusions are listed or explicitly marked `none`.
- **HANDOFF-DONE-006**: Recommended orchestration review and next actions are provided.
