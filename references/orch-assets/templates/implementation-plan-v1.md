---
id: plan-YYYYMMDD-001
goal: [Concise Title Describing the Implementation Plan Goal]
purpose: [upgrade|refactor|feature|data|infrastructure|process|architecture|design]
component: [target component/module/system]
version: 1
date_created: YYYY-MM-DD
last_updated: YYYY-MM-DD
owner: [team/individual/agent]
status: Planned
tags:
  - [feature|upgrade|chore|architecture|migration|bug|data|process]
source_knowledge:
  - .work-bundle/knowledge/notes/...
phase_index:
  - id: phase-001
    name: [Phase Name]
    path: .work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug].md
    status: Planned
    depends_on: []
---

# Introduction

![Status: <status>](https://img.shields.io/badge/status-<status>-<status_color>)

[A short concise introduction to the plan and the goal it is intended to achieve.]

## 1. Requirements & Constraints

- **REQ-001**: [Functional requirement.]
- **SEC-001**: [Security requirement.]
- **CON-001**: [Implementation constraint.]
- **GUD-001**: [Guideline to follow.]
- **PAT-001**: [Project pattern to follow.]
- **[3 LETTERS]-001**: [Other Requirement 1]
    - **COMPAT-001**: [Compatibility requirement.]
    - **DATA-001**: [Data model requirement.]
    - **API-001**: [API/interface requirement.]
    - **TEST-001**: [Testing requirement.]

## 2. Implementation Phases

### Phase Index

| Phase | Name | Path | Status | Depends On | Parallelizable |
|---|---|---|---|---|---|
| phase-001 | [Phase Name] | `.work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug].md` | Planned | - | true |

## 3. Alternatives

- **ALT-001**: [Alternative approach.]  
  **Rejected Because**: [Concrete reason.]
- **ALT-002**: [Alternative approach.]  
  **Rejected Because**: [Concrete reason.]

## 4. Files

| ID | Path | Purpose | Operation | Related Phase |
|---|---|---|---|---|
| FILE-001 | `[exact file path]` | [Why this file is affected.] | create/update/delete/read | phase-001 |
| FILE-002 | `[exact file path]` | [Why this file is affected.] | create/update/delete/read | phase-001 |

## 5. API / Interface Impact

- **API-001**: [Endpoint/function/interface/event affected.]
  - **Change**: [Exact required change.]
  - **Compatibility**: [Compatibility rule.]

## 6. Data Model Impact

- **DATA-001**: [Entity/table/schema/state affected.]
  - **Change**: [Exact required change.]
  - **Migration Required**: true|false
  - **Compatibility**: [Compatibility rule.]

## 7. Testing

- **TEST-001**: [Exact test to implement or run.]
  - **Target**: [file/module/function/API.]
  - **Expected Result**: [Measurable result.]
- **TEST-002**: [Exact test to implement or run.]
  - **Target**: [file/module/function/API.]
  - **Expected Result**: [Measurable result.]

## 8. Risks & Assumptions

- **RISK-001**: [Risk.]
  - **Mitigation**: [Concrete mitigation.]
- **ASSUMPTION-001**: [Assumption.]
  - **Validation**: [How to verify.]

## 9. Open Questions

- **OQ-001**: [Question blocking executable implementation.]
  - **Required Decision**: [Specific decision needed.]
  - **Blocked Phase/Task**: [phase/task id.]

## 10. Completion Criteria

- **DONE-001**: [Measurable final completion criterion.]
- **DONE-002**: [Measurable final completion criterion.]
- **DONE-003**: [Validation/test criterion.]

## 11. Related Specifications / Further Reading

- [Related spec or plan](path)
- [Relevant durable knowledge](.work-bundle/knowledge/notes/...)
---
id: plan-YYYYMMDD-001
goal: [Concise Title Describing the Implementation Plan Goal]
purpose: [upgrade|refactor|feature|data|infrastructure|process|architecture|design]
component: [target component/module/system]
version: 1
date_created: YYYY-MM-DD
last_updated: YYYY-MM-DD
owner: [team/individual/agent]
status: Planned
tags:
  - [feature|upgrade|chore|architecture|migration|bug|data|process]
source_spec:
  - .work-bundle/orchestration/spec/active/...
source_knowledge:
  - .work-bundle/knowledge/notes/...
phase_index:
  - id: phase-001
    name: [Phase Name]
    path: .work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug].md
    status: Planned
    depends_on: []
    parallelizable: true
---

# Implementation Plan: [Plan Goal]

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Introduction

[Short, concrete introduction explaining what this plan implements, which specification it derives from, and the intended outcome.]

## 1. Requirements & Constraints

- **REQ-001**: [Functional requirement.]
- **SEC-001**: [Security requirement.]
- **CON-001**: [Implementation constraint.]
- **GUD-001**: [Guideline to follow.]
- **PAT-001**: [Project pattern to follow.]
- **COMPAT-001**: [Compatibility requirement.]
- **DATA-001**: [Data model requirement.]
- **DOMAIN-001**: [Domain model requirement.]
- **API-001**: [API/interface requirement.]
- **TEST-001**: [Testing requirement.]

## 2. Source Specification & Knowledge

| ID | Type | Path | Required Application |
|---|---|---|---|
| SRC-001 | specification | `.work-bundle/orchestration/spec/active/...` | [How the spec constrains this plan.] |
| KNOW-001 | architecture | `.work-bundle/knowledge/notes/...` | [Accepted project knowledge used by this plan.] |
| KNOW-002 | data-model | `.work-bundle/knowledge/notes/...` | [Accepted project knowledge used by this plan.] |

## 3. Phase Map

| Phase | Name | Path | Status | Depends On | Parallelizable | Completion Gate |
|---|---|---|---|---|---|---|
| phase-001 | [Phase Name] | `.work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug].md` | Planned | - | true | [Measurable completion gate.] |
| phase-002 | [Phase Name] | `.work-bundle/orchestration/plan/active/[plan-id]/phase-002-[slug].md` | Planned | phase-001 | true|false | [Measurable completion gate.] |

## 4. Desired Files

| ID | File Type | Path | Purpose | Operation | Related Phase |
|---|---|---|---|---|---|
| FILE-API-001 | api | `[exact API/controller/interface file path]` | [Why this file is needed.] | create/update/delete/read | phase-001 |
| FILE-DATA-001 | data-model | `[exact entity/schema/migration file path]` | [Why this file is needed.] | create/update/delete/read | phase-001 |
| FILE-DOMAIN-001 | domain-model | `[exact domain model file path]` | [Why this file is needed.] | create/update/delete/read | phase-001 |
| FILE-TEST-001 | unit-test | `[exact test file path]` | [What behavior this test validates.] | create/update/delete/read | phase-002 |
| FILE-PAGE-001 | page | `[exact page/view/component file path]` | [Why this page/component is needed.] | create/update/delete/read | phase-002 |
| FILE-DOC-001 | documentation | `[exact documentation file path]` | [Why this document is needed.] | create/update/delete/read | phase-002 |

## 5. Alternatives

- **ALT-001**: [Alternative approach.]
  - **Status**: pending|accepted|rejected
  - **Decision Required Before**: [phase-id/task-id]
  - **Accepted When**: [Deterministic acceptance condition.]
  - **Rejected Because**: [Concrete rejection reason, if rejected.]
- **ALT-002**: [Alternative approach.]
  - **Status**: pending|accepted|rejected
  - **Decision Required Before**: [phase-id/task-id]
  - **Accepted When**: [Deterministic acceptance condition.]
  - **Rejected Because**: [Concrete rejection reason, if rejected.]

## 6. Open Questions

- **OQ-001**: [Question blocking executable implementation.]
  - **Required Decision**: [Specific decision needed.]
  - **Must Be Resolved Before**: [phase-id/task-id]
  - **Fallback If Unresolved**: [Stop execution|use declared assumption|skip affected task]
- **OQ-002**: [Question blocking executable implementation.]
  - **Required Decision**: [Specific decision needed.]
  - **Must Be Resolved Before**: [phase-id/task-id]
  - **Fallback If Unresolved**: [Stop execution|use declared assumption|skip affected task]

## 7. Tests

Test phases may execute together when their dependencies are satisfied and no shared mutable resource conflict exists.

| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |
|---|---|---|---|---|---|---|
| TEST-001 | unit | `[file/module/function/API]` | phase-001 | TEST-002 | `[command if applicable]` | [Measurable result.] |
| TEST-002 | integration | `[file/module/function/API]` | phase-002 | TEST-001 | `[command if applicable]` | [Measurable result.] |

## 8. Completion Criteria

- **DONE-REQ-001**: All requirements in `## 1. Requirements & Constraints` are validated or explicitly marked not applicable with reason.
- **DONE-CON-001**: All constraints in `## 1. Requirements & Constraints` are validated with concrete evidence.
- **DONE-TEST-001**: All required tests in `## 7. Tests` pass or have documented failure reason and remediation task.
- **DONE-ACH-001**: The implementation achieves the stated plan goal.
- **DONE-FILE-001**: All desired files are created, updated, deleted, or confirmed unnecessary according to the plan.
- **DONE-HANDOFF-001**: Executor invokes the `create-handoff` directive and creates a plan-scoped `executor-result` handoff under `.work-bundle/orchestration/handoff/executor/active/` before reporting the root plan as completed or blocked.

## 9. Related Specifications / Further Reading

- [Related specification](.work-bundle/orchestration/spec/active/...)
- [Relevant durable knowledge](.work-bundle/knowledge/notes/...)

---

# Phase Template

---
id: phase-001
plan_id: plan-YYYYMMDD-001
name: [Phase Name]
goal: [Concrete measurable phase goal]
status: Planned
order: 1
date_created: YYYY-MM-DD
last_updated: YYYY-MM-DD
owner: [team/individual/agent]
depends_on: []
parallelizable: true
path: .work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug].md
source_spec:
  - .work-bundle/orchestration/spec/active/...
source_knowledge:
  - .work-bundle/knowledge/notes/...
task_index:
  - id: task-001
    name: [Task Name]
    path: .work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug]/task-001-[slug].md
    status: Planned
    depends_on: []
completion_criteria:
  - [measurable completion criterion]
---

# Phase 001: [Phase Name]

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Introduction

[Short, concrete explanation of what this phase does and what exact outcome it must produce.]

## 1. Requirements & Constraints

- **REQ-001**: [Requirement this phase must satisfy.]
- **SEC-001**: [Security requirement this phase must satisfy.]
- **CON-001**: [Constraint this phase must obey.]
- **GUD-001**: [Guideline this phase must follow.]
- **PAT-001**: [Pattern this phase must follow.]
- **DATA-001**: [Data requirement for this phase.]
- **DOMAIN-001**: [Domain requirement for this phase.]
- **API-001**: [API/interface requirement for this phase.]
- **TEST-001**: [Testing requirement for this phase.]

## 2. Dependencies

### 2.1 Alternative Dependencies

| Alternative | Required Decision | Must Be Determined Before Task | If Unresolved |
|---|---|---|---|
| ALT-001 | [accept/reject decision] | task-001 | stop execution|use declared assumption|skip affected task |

### 2.2 Open Question Dependencies

| Open Question | Required Resolution | Must Be Resolved Before Task | If Unresolved |
|---|---|---|---|
| OQ-001 | [specific answer required] | task-001 | stop execution|use declared assumption|skip affected task |

### 2.3 File Dependencies

| Required File | Must Exist Before Task | Validation Method |
|---|---|---|
| `[exact file path]` | task-001 | [How to confirm the file exists and is usable.] |

### 2.4 Task Dependencies

| Task | Depends On | Dependency Type | Reason |
|---|---|---|---|
| task-002 | task-001 | output|decision|file|test | [Why this dependency exists.] |

## 3. Task Map

Resolve alternatives and open questions as leading tasks before implementation tasks.

| Task | Name | Path | Status | Depends On | Parallelizable | Task Type |
|---|---|---|---|---|---|---|
| task-001 | Resolve Alternative ALT-001 | `.work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug]/task-001-resolve-alt-001.md` | Planned | - | false | decision |
| task-002 | Resolve Open Question OQ-001 | `.work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug]/task-002-resolve-oq-001.md` | Planned | - | false | decision |
| task-003 | [Implementation Task] | `.work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug]/task-003-[slug].md` | Planned | task-001, task-002 | true | implementation |
| task-004 | [Test Task] | `.work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug]/task-004-[slug].md` | Planned | task-003 | true | test |

## 4. Tests

Tests must validate that the implemented model functions as designed.

| ID | Test Type | Target | Related Task | Command | Expected Result |
|---|---|---|---|---|---|
| TEST-001 | unit | `[file/module/function/API]` | task-003 | `[command if applicable]` | [Measurable result.] |
| TEST-002 | model-behavior | `[data/domain/API model]` | task-003 | `[command if applicable]` | [Model functions as designed.] |

## 5. Completion Criteria

Complete this section after the phase is completed.

- **DONE-REQ-001**: [Requirement validation result and evidence.]
- **DONE-CON-001**: [Constraint validation result and evidence.]
- **DONE-TEST-001**: [Test result summary.]
- **DONE-ACH-001**: [Phase achievement summary.]
- **DONE-HANDOFF-001**: Executor invokes the `create-handoff` directive and creates a phase-scoped `executor-result` handoff under `.work-bundle/orchestration/handoff/executor/active/` before reporting this phase as completed or blocked.

## 6. Executor Handoff Requirements

The executor must invoke the `create-handoff` directive at the end of this phase and create a phase-scoped `executor-result` handoff before returning final phase status.

The executor must report:

- files changed
- symbols changed
- tasks completed
- tests run
- test results
- deviations from this phase file
- unresolved issues
- suggested durable conclusions

---

# Task Template

---
id: task-001
plan_id: plan-YYYYMMDD-001
phase_id: phase-001
name: [Task Name]
status: Planned
order: 1
task_type: decision|implementation|test|documentation|handoff
date_created: YYYY-MM-DD
last_updated: YYYY-MM-DD
owner: [team/individual/agent]
depends_on: []
source_files:
  - [exact source file path]
target_files:
  - [exact target file path]
target_symbols:
  - [class/function/module/interface name]
completion_criteria:
  - [measurable completion criterion]
---

# TASK-001: [Task Name]

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## 1. Goals

- **GOAL-001**: [Concrete goal this task must achieve.]
- **GOAL-002**: [Concrete goal this task must achieve.]

## 2. Dependencies

| ID | Type | Related Task | Required State | Reason |
|---|---|---|---|---|
| DEP-001 | decision|open-question|file|task|test|external | task-000|N/A | [required state] | [Why this dependency exists.] |

## 3. Source Files

| ID | Path | Required Usage |
|---|---|---|
| SRC-001 | `[exact source file path]` | [How this source file must be read, reused, or modified.] |

## 4. Target Files

| ID | Path | Operation | Required Change |
|---|---|---|---|
| FILE-001 | `[exact target file path]` | create/update/delete/read | [Exact required change.] |

## 5. Implementation Instructions

1. [Exact implementation instruction.]
2. [Exact implementation instruction.]
3. [Exact implementation instruction.]

## 6. Validation

1. [Exact validation command, test, inspection, or expected result.]
2. [Exact validation command, test, inspection, or expected result.]

## 7. Completion Criteria

- **DONE-GOAL-001**: All goals in `## 1. Goals` are achieved with concrete evidence.
- **DONE-TEST-001**: Required tests pass or failures are documented with remediation task.
- **DONE-HANDOFF-001**: Executor invokes the `create-handoff` directive and creates a task-scoped `executor-result` handoff under `.work-bundle/orchestration/handoff/executor/active/` before reporting this task as completed or blocked.
