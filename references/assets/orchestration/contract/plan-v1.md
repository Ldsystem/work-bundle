---
id: plan-YYYYMMDD-001
goal: [Concise title describing the implementation plan goal]
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

Use a compact source-spec ID map. Do not paste long specification sections into the plan.

- **SPEC-REQ-001**: `REQ-001` — [one-line execution impact.]
- **SPEC-AC-001**: `AC-001` — [one-line acceptance impact.]
- **SPEC-CON-001**: `CON-001` — [one-line constraint impact.]
- **SPEC-OQ-001**: `OQ-001` — [one-line decision/blocker impact.]
- **PLAN-REQ-001**: [Plan-only execution requirement, if needed.]

## 2. Source Specification & Knowledge

| ID | Type | Path | Required Application |
|---|---|---|---|
| SRC-001 | specification | `.work-bundle/orchestration/spec/active/...` | [How the spec constrains this plan.] |
| CTX-001 | carried-context | `source specification` | [Accepted project knowledge is already carried in the spec; do not require plan executors to read `.work-bundle/knowledge/`.] |

## 3. Phase Map

| Phase | Name | Path | Status | Depends On | Parallelizable | Completion Gate |
|---|---|---|---|---|---|---|
| phase-001 | [Phase Name] | `.work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug].md` | Planned | - | true | [Measurable completion gate.] |

## 4. Desired Files

| ID | File Type | Path | Purpose | Operation | Related Phase |
|---|---|---|---|---|---|
| FILE-001 | [api|data-model|domain-model|unit-test|page|documentation|other] | `[exact path]` | [Why this file is needed.] | create/update/delete/read | phase-001 |

## 5. Alternatives

- **ALT-001**: [Alternative approach.]
  - **Status**: pending|accepted|rejected
  - **Decision Required Before**: [phase-id/task-id]
  - **Accepted When**: [Deterministic acceptance condition.]
  - **Rejected Because**: [Concrete rejection reason, if rejected.]

## 6. Open Questions

- **OQ-001**: [Question blocking executable implementation.]
  - **Required Decision**: [Specific decision needed.]
  - **Must Be Resolved Before**: [phase-id/task-id]
  - **Fallback If Unresolved**: stop execution|use declared assumption|skip affected task

## 7. Tests

| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |
|---|---|---|---|---|---|---|
| TEST-001 | unit|integration|model-behavior|manual | `[file/module/function/API]` | phase-001 | - | `[command if applicable]` | [Measurable result.] |

## 8. Generated Artifact Verification

Record the verification pass performed after generating the root plan, phases, and tasks.

| ID | Check | Scope | Result | Repair |
|---|---|---|---|---|
| VERIFY-001 | source-spec ID coverage maps every implemented requirement, constraint, resolved alternative, and resolved open question to plan/phase/task artifacts. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-002 | Exact artifact paths, source files, target files, dependencies, task ordering, validation commands, and completion criteria are internally consistent. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-003 | Safe parallelization is exposed where dependencies and write scopes allow, and unsafe parallelization is explicitly blocked by dependency or scope evidence. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-004 | Every task, phase, and plan completion path requires `create-handoff` with an `executor-result` handoff. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |

If any generated artifact drifts from the source specification, omits required spec-ID coverage, contains inconsistent paths or dependencies, lacks validation, or lacks handoff criteria, repair the generated artifacts in the same planning turn and repeat this verification. If the source specification itself has unresolved questions, missing stable IDs, missing evidence, or contradictory instructions, stop for specification repair instead of inventing plan content.

## 9. Completion Criteria

- **DONE-REQ-001**: All requirements are validated or explicitly marked not applicable with reason.
- **DONE-CON-001**: All constraints are validated with concrete evidence.
- **DONE-TEST-001**: Required tests pass or have documented failure reason and remediation task.
- **DONE-ACH-001**: The implementation achieves the stated plan goal.
- **DONE-FILE-001**: Desired files are created, updated, deleted, or confirmed unnecessary.
- **DONE-VERIFY-001**: Generated root plan, phase, and task artifacts were verified against the source specification and repaired for drift, gaps, dependencies, validations, safe parallelization, and handoff requirements before completion.
- **DONE-HANDOFF-001**: Executor invokes `create-handoff` and creates a plan-scoped `executor-result` handoff under `.work-bundle/orchestration/handoff/executor/active/` before reporting the root plan as completed or blocked.

## 10. Related Specifications / Further Reading

- [Related specification](.work-bundle/orchestration/spec/active/...)
- [Relevant durable knowledge](.work-bundle/knowledge/notes/...)
