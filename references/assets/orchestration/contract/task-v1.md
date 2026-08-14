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
source_ids: [REQ-001, AC-001]
truth_basis:
  purpose: [one bounded intended outcome]
  as_is_evidence: [[exact source, test, or harness evidence]]
  decision_authority: [[accepted source IDs]]
  expected_delta: [[observable post-change behavior]]
  conflict_status: clear|escalate
source_files:
  - [exact source file path]
target_files:
  - [exact target file path]
target_symbols:
  - [class/function/module/interface]
completion_criteria:
  - [measurable criterion]
methodology:
  primary: tdd|systematic-debugging|direct|loop-coding
  required_skills:
    - [skill-name]
executor_profile:
  capability: mechanical|standard|judgment
  context_mode: compiled-brief
  review_capability: standard|judgment
  escalation:
    after_failed_repairs: 2
    next_capability: standard|judgment
acceptance_review:
  required: true
  reviewer_independent: false
  verdict: pending
  reviewed_head: ""
  findings: []
allocated_rules:
  - id: [rule-id]
    source: [authority source]
    path: [file path when file-backed]
    applies_when: [observable task condition]
    load_timing: before_task_work|before_source_inspection|before_script_edit|before_rule_edit|before_validation
    enforcement: must|should
allocated_skills:
  - name: [skill-name]
    source: [authority source]
    path: [file path when file-backed]
    applies_when: [observable task condition]
    use_timing: before_task_work|task_execution|validation
    required_for: [why required]
---

# TASK-001: [Task Name]

## Goal

[One bounded outcome.]

## Truth Basis

The front-matter `truth_basis` is mandatory and uses the same five fields as the lightweight path. Every `decision_authority` entry must be an accepted ID already present in the task's `source_ids`; arbitrary prose and unallocated linked-spec IDs fail closed. The compiler resolves those IDs only from linked accepted specifications, carries the exact basis into the disposable task brief and review package, and returns the existing `decision-blocked` route when `conflict_status` is `escalate`. Executors do not retrieve durable knowledge to rebuild this authority.

## Source references

List stable source IDs and their task-local effect. Do not duplicate full specification prose.

| ID | Source path | Task-local effect |
| --- | --- | --- |
| REQ-001 | `.work-bundle/orchestration/spec/active/example.md` | [effect] |

## Dependencies and contracts

| Dependency | Required state | Reason |
| --- | --- | --- |
| task-000 | Completed | [reason] |

For contract-decoupled work, name the common contract group, accepted prior handoffs, barrier, allowed validation scope, forbidden sibling validation, and convergence owner.

## Files and interfaces

| Path or interface | Read/write | Required usage |
| --- | --- | --- |
| `path/to/file` | write | [exact change] |

## Implementation

1. [Concrete file or symbol action.]
2. [Concrete file or symbol action.]

## Validation

| Command or inspection | Proves | Expected |
| --- | --- | --- |
| `exact command` | [claim] | [result] |

## Completion

- Implementation criteria are satisfied.
- Fresh task validation evidence exists.
- The compiled task brief and review package carry the same accepted Truth Basis.
- A valid `executor-result-v1` handoff exists.
- When `acceptance_review.required` is true, `acceptance_review.verdict` is `accept`.

## Planning verification

Before planning completes, view this task through the plan's semantic-convergence lenses: source-ID coverage, exact file and interface scope, dependencies, validation ownership, allocated rules and methodology, parallel/barrier safety, and compiled executor-context completeness. Repair discovered defects and record compact `semantic_loop` evidence at the owning plan level.

The executor normally consumes the compiled task brief, task-scoped source/tests, and allocated methodology skill. Full specification, root-plan, or phase reading is an escalation path when compiled context is inconsistent or review finds a source-contract defect.

## Methodology and capability allocation

- `mechanical`: one or two files with exact contracts and commands and little judgment.
- `standard`: multi-file coordination, pattern matching, debugging, or integration.
- `judgment`: architecture, concurrency, ambiguous tradeoffs, or high-risk review.
- Semantic artifacts allocate `dev-semantic-convergence`.
- Unexpected behavior allocates `dev-systematic-debugging`; diagnosed testable repair also allocates TDD.
- New or changed testable behavior allocates `dev-test-driven-development`.
- Acceptance review allocates `dev-code-review`.
- Configuration, generated, or non-testable mechanical work uses `direct` plus exact deterministic verification.
