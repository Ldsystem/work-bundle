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
  - carried by source specification
task_index:
  - id: task-001
    name: [Task Name]
    path: .work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug]/task-001-[slug].md
    status: Planned
    depends_on: []
allocated_rules:
  - id: [rule-id]
    source: AGENTS.md|work-bundle-toolkit|work-bundle-global|work-bundle-project|builtin|plugin|other
    path: [file path when file-backed, otherwise source label]
    applies_when: [observable phase condition]
    load_timing: before_task_work|before_rule_edit|before_script_edit|before_validation
    enforcement: must|should
allocated_skills:
  - name: [skill-name]
    source: work-bundle|agents-skills|codex-skills|builtin|plugin|other
    path: [file path when file-backed, otherwise source label]
    applies_when: [observable phase condition]
    use_timing: task_execution|phase_validation
    required_for: [why child executors need this skill context]
completion_criteria:
  - [measurable completion criterion]
---

# Phase 001: [Phase Name]

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Introduction

[Short, concrete explanation of what this phase does and what exact outcome it must produce.]

## 1. Requirements & Constraints

List only the source-spec IDs this phase implements or validates. Do not paste full specification prose here.

- **SPEC-REQ-001**: `REQ-001` — [one-line execution impact for this phase.]
- **SPEC-AC-001**: `AC-001` — [one-line validation impact for this phase.]
- **SPEC-CON-001**: `CON-001` — [one-line constraint impact for this phase.]
- **SPEC-OQ-001**: `OQ-001` — [one-line decision impact for this phase.]

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

### 2.5 Barrier Participants

Include this table when the phase contains contract-decoupled parallel tasks.

| Barrier | Contract Group | Participants | Readiness Criteria | Release Condition | Convergence Task |
|---|---|---|---|---|---|
| BAR-001 | CG-001 | task-002, task-003 | each participant completes or blocks with executor-result handoff | all participants reached barrier | task-004 |

Participants validate against the common contract group, accepted prior handoffs, and their task-local files. They must not validate against sibling in-progress files or classify sibling work as stale before the convergence task.

## 3. Task Map

Resolve alternatives and open questions as leading tasks before implementation tasks.

| Task | Name | Path | Status | Depends On | Parallelizable | Task Type |
|---|---|---|---|---|---|---|
| task-001 | Resolve Alternative ALT-001 | `.work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug]/task-001-resolve-alt-001.md` | Planned | - | false | decision |
| task-002 | [Implementation Task] | `.work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug]/task-002-[slug].md` | Planned | task-001 | true | implementation |

## 4. Tests

| ID | Test Type | Target | Related Task | Command | Expected Result |
|---|---|---|---|---|---|
| TEST-001 | unit|integration|model-behavior|manual | `[file/module/function/API]` | task-002 | `[command if applicable]` | [Measurable result.] |

## 5. Generated Artifact Verification

Record phase-level verification against the source specification and root plan.

| ID | Check | Result | Repair |
|---|---|---|---|
| VERIFY-001 | Phase requirements cite the relevant source-spec IDs and do not duplicate long specification prose. | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-002 | Task map paths, dependencies, ordering, and safe parallelization flags match exact task write scopes and root-plan sequencing. | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-003 | Phase tests, completion criteria, and compact phase-scoped `executor-result` handoff requirement are present and consistent with child tasks. | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-004 | Phase `allocated_rules` and `allocated_skills` cover phase-wide signals and are carried into child tasks where executors need them. | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-005 | Barrier participant maps, post-barrier convergence dependencies, and contract-only validation boundaries are present when parallel tasks share a contract. | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |

Repair generated phase or child-task drift, missing spec-ID alignment, dependency mistakes, unsafe parallelization, validation gaps, allocation gaps, and handoff gaps in the same planning turn. Stop for specification repair when the source spec cannot support a deterministic phase.

## 6. Completion Criteria

- **DONE-REQ-001**: [Requirement validation result and evidence.]
- **DONE-CON-001**: [Constraint validation result and evidence.]
- **DONE-TEST-001**: [Test result summary.]
- **DONE-ACH-001**: [Phase achievement summary.]
- **DONE-BARRIER-001**: [Barrier readiness and convergence result when applicable.]
- **DONE-VERIFY-001**: Phase and child task artifacts were verified against source-spec IDs, dependencies, safe parallelization, validation, and handoff requirements before completion.
- **DONE-HANDOFF-001**: Executor invokes `create-handoff` and creates a compact phase-scoped `executor-result` handoff under `.work-bundle/orchestration/handoff/executor/active/` before reporting this phase as completed or blocked.

## 7. Executor Handoff Requirements

The executor must invoke `create-handoff` at the end of this phase and create a sparse YAML `executor-result` handoff. Include only applicable continuation and review evidence: completed tasks, changed or inspected files, symbols when useful, validation commands and results, unresolved blockers, phase-fit or task-fit evidence, repository/preflight evidence, compact CodeGraph evidence when source-code work was in scope, delegation_evidence when ownership was delegated, and Knowledge Base Update disposition when review must carry it forward. Omit empty sections, deviation narratives, durable-knowledge advice, next-action recommendations, and other executor advice fields.
