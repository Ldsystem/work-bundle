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
allocated_rules:
  - id: [rule-id]
    source: AGENTS.md|work-bundle-toolkit|work-bundle-global|work-bundle-project|builtin|plugin|other
    path: [file path when file-backed, otherwise source label]
    applies_when: [observable task condition]
    load_timing: before_task_work|before_source_inspection|before_script_edit|before_rule_edit|before_validation
    enforcement: must|should
allocated_skills:
  - name: [skill-name]
    source: work-bundle|agents-skills|codex-skills|builtin|plugin|other
    path: [file path when file-backed, otherwise source label]
    applies_when: [observable task condition]
    use_timing: before_task_work|task_execution|validation
    required_for: [why this executor must use or be aware of the skill]
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

For contract-decoupled parallel tasks, dependencies must name the common contract group and any accepted prior handoffs. Do not list sibling in-progress implementation tasks as dependencies merely to enable validation.

## 3. Source Files

| ID | Path | Required Usage |
|---|---|---|
| SRC-001 | `[exact source file path]` | [How this source file must be read, reused, or modified.] |

When a task is a barrier participant, include the exact common contract artifact paths in `source_files` or a task-local contract table. Exclude sibling target files unless they are accepted prior handoffs or assigned post-barrier convergence inputs.

## 4. Target Files

| ID | Path | Operation | Required Change |
|---|---|---|---|
| FILE-001 | `[exact target file path]` | create/update/delete/read | [Exact required change.] |

## 5. Implementation Instructions

1. [Exact implementation instruction.]
2. [Exact implementation instruction.]
3. [Exact implementation instruction.]

Instructions must be concrete file-level execution steps. Do not restate the full source specification. Use the spec references above for requirement meaning.

Before implementation, the executor must load, use, acknowledge, or condition-evaluate every task-level `allocated_rules` entry and every task-level `allocated_skills` entry according to its source, `load_timing`, `use_timing`, enforcement, and required-for reason. File-backed entries use `path`; non-file-backed entries use `source` as the authority label. If an allocated rule or skill is unavailable, stale, or inapplicable, record the concrete reason in the executor-result handoff.

When source-code inspection or edits are in scope, include concise task-level CodeGraph expectations:

- identify each target repository or local project root when known;
- state whether CodeGraph is applicable when `.codegraph/` exists, or require the executor to record no-index fallback;
- require a `codegraph:` evidence block in the executor-result handoff when source-code work is in scope;
- require `pre_inspection_sync` before graph-derived inspection when CodeGraph is available;
- require `post_change_sync` before final graph impact validation when indexed source changes;
- require accepted fallback evidence such as `no-index` or `sync-failed` when CodeGraph is not used.

When task ownership may be delegated, include concise delegation evidence expectations:

- require visible multi-agent subagent delegation when delegation is used in Codex app contexts;
- require a `delegation_evidence:` block in the executor-result handoff;
- require `visible_reference` when the environment provides one;
- require `surface: multi-agent-subagent` for delegated task ownership in this environment, or `single-agent-fallback` when visible delegation is unavailable or unsafe;
- require `internal_spawn_used_for_task_delegation: false`;
- require cross-conversation delegation and invisible internal spawn workers not to own task execution;
- allow internal helper workers only when they do not own delegated task execution.

When the task participates in a contract group, include concise contract-decoupling expectations:

- `common_contract_group`: ID and exact contract artifact paths.
- `barrier`: barrier ID, participant role, and expected readiness evidence.
- `allowed_validation_scope`: common contract, accepted prior handoffs, task-local files, and declared validation commands.
- `forbidden_peer_validation`: sibling in-progress implementation files, sibling unaccepted handoffs, and pre-barrier cross-branch checks.
- `convergence_owner`: task ID that owns post-barrier joint debug or integration validation.

## 6. Validation

1. [Exact validation command, test, inspection, or expected result.]
2. [Exact validation command, test, inspection, or expected result.]

Contract-decoupled participant validation must prove the task against the common contract and task-local scope only. Cross-branch behavior checks are skipped or deferred until the declared convergence owner runs after barrier release.

## 7. Generated Artifact Integrity

Before reporting planning complete, verify this generated task artifact against the source specification, root plan, and parent phase:

- relevant source-spec IDs are cited and only task-specific execution detail is added;
- source files, target files, target symbols, dependencies, implementation instructions, validation commands, and completion criteria are exact and internally consistent;
- allocated rules and allocated skills from any agent-visible source cover the task's material operation signals and are scoped to what the executor must know before work;
- task write scope supports the parent phase's safe parallelization decision;
- the task requires `create-handoff` and a task-scoped `executor-result` handoff before completed or blocked status is reported.

Repair generated task drift, missing coverage, invalid dependencies, broad or inconsistent paths, validation gaps, and handoff gaps in the same planning turn. If the source specification lacks stable IDs, evidence, or resolved decisions needed for the task, stop for specification repair.

## 8. Completion Criteria

- **DONE-GOAL-001**: All goals in `## 1. Goals` are achieved with concrete evidence.
- **DONE-TEST-001**: Required tests pass or failures are documented with remediation task.
- **DONE-CONTRACT-001**: Contract-only validation, forbidden peer validation, barrier readiness, and convergence ownership are recorded when applicable.
- **DONE-VERIFY-001**: This generated task artifact was verified against the source specification, root plan, and parent phase for spec-ID coverage, exact paths, dependencies, validation, and handoff requirements.
- **DONE-HANDOFF-001**: Executor invokes `create-handoff` and creates a compact task-scoped `executor-result` handoff under `.work-bundle/orchestration/handoff/executor/active/` before reporting this task as completed or blocked. The handoff is sparse YAML by default and includes only applicable changed-file, validation, unresolved-blocker, task-fit, repository, CodeGraph, delegation_evidence, and Knowledge Base Update disposition carry-forward fields.
