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

## 1.1 Spec References

List the exact source-spec IDs this task implements or validates. Do not paste full specification prose here.

- **SPEC-REQ-001**: `REQ-001` — [one-line task impact.]
- **SPEC-AC-001**: `AC-001` — [one-line validation impact.]
- **SPEC-CON-001**: `CON-001` — [one-line constraint impact.]
- **SPEC-OQ-001**: `OQ-001` — [one-line decision or blocker impact.]

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

Instructions must be concrete file-level execution steps. Do not restate the full source specification. Use the spec references above for requirement meaning.

## 6. Validation

1. [Exact validation command, test, inspection, or expected result.]
2. [Exact validation command, test, inspection, or expected result.]

## 7. Completion Criteria

- **DONE-GOAL-001**: All goals in `## 1. Goals` are achieved with concrete evidence.
- **DONE-TEST-001**: Required tests pass or failures are documented with remediation task.
- **DONE-HANDOFF-001**: Executor invokes `create-handoff` and creates a task-scoped `executor-result` handoff under `.work-bundle/orchestration/handoff/executor/active/` before reporting this task as completed or blocked.
