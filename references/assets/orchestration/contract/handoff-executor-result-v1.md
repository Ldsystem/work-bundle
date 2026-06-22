---
id: handoff-executor-result-v1
type: contract
status: active
artifact_type: executor-result-handoff
default_format: yaml
---

# Executor Result Handoff Contract

Executor-result handoffs are compact continuation artifacts from an executor to the orchestration agent. They default to sparse YAML and record only facts needed for continuation, review, and safety validation.

Templates define the maximum available fields, not mandatory output shape. Omit optional blocks when they do not apply.

## Default Path

```text
.work-bundle/orchestration/handoff/executor/active/handoff-exec-YYYYMMDD-001-slug.yaml
```

## Sparse YAML Schema

```yaml
id: handoff-exec-YYYYMMDD-001-slug
type: executor-result
status: active
project: work-bundle
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
related:
  spec: spec-id-or-null
  plan: plan-id-or-null
  phase: phase-id-or-null
  task: task-id-or-null

result:
  state: completed | blocked | partial | failed
  summary: "One or two sentences maximum."

changes:
  files:
    - path: path/to/file
      action: created | modified | deleted | inspected
      symbols: []
      notes: "Only when needed."

validation:
  commands:
    - command: "exact command"
      result: passed | failed | skipped
      note: "Failure reason or skip reason only."

unresolved:
  - "Only include blockers or issues that remain."

task_fit_check:
  task: path-or-id
  result: clean | repaired | unresolved | skipped
  artifacts_checked:
    - related specification
    - root plan
    - parent phase
    - assigned task
  findings: []

repository:
  - root: /absolute/path
    target_kind: git-backed | local-project
    preflight_kind: git-clean-worktree | local-project
    baseline: initial | accepted-handoff
    status: clean | blocked

codegraph:
  - root: /absolute/path
    applicable: true | false
    up_to_date: true | false
    reason: null | no-index | sync-failed | not-source-code | blocked

delegation_evidence:
  delegated: true | false
  surface: visible-thread | visible-worktree | visible-thread-and-worktree | single-agent-fallback | blocked
  visible_reference: null
  internal_spawn_used_for_task_delegation: false
  internal_workers_used_for_support: false
  fallback_reason: null
```

## Required By Applicability

- `id`, `type`, `status`, `project`, `created_at`, `related`, and `result` are always required.
- `changes.files` is required when files, symbols, artifacts, schemas, commands, or docs changed or were inspected as the task output.
- `validation.commands` is required when any command, test, lint, inspection, or manual verification was run or intentionally skipped.
- `unresolved` is included only when blockers or issues remain.
- `task_fit_check` is required for completed and partial task results. It records the assigned task, result `clean|repaired|unresolved|skipped`, artifacts checked, and meaningful findings.
- `repository` is required when repository preflight, accepted baseline, changed paths, or blocker state matters for continuation.
- `codegraph` is required when source-code inspection or edits were in scope. Keep it compact: `root`, `applicable`, `up_to_date`, and required fallback or blocker facts are enough unless a failure needs detail.
- `delegation_evidence` is required when task, phase, or plan ownership was delegated or when the execution path needs proof that invisible internal spawn did not own delegation.

## Forbidden Executor-Result Fields

Validation must reject executor-result handoffs that contain these top-level fields:

```yaml
suggested_durable_conclusions: []
durable_candidate_facts: []
recommended_orchestration_review: []
recommended_next_actions: []
delegation: {}
deviations: []
strategy_advice: []
knowledge_persistence: []
```

Use `delegation_evidence` for compact delegation proof. Use `unresolved` and `task_fit_check.findings` for remaining issues instead of `deviations`.

## Safety Evidence

Compact handoffs must not weaken safety gates:

- Repository evidence must preserve root, target kind, preflight kind, baseline, and clean or blocked result when applicable.
- CodeGraph evidence must preserve no-index fallback, sync-failed, stale, or blocker facts when applicable.
- Delegation evidence must preserve visible surface, visible reference when available, and `internal_spawn_used_for_task_delegation: false`.
- Validation evidence must list exact commands or inspections and their result.
- Task-fit evidence must prove the result was checked against the related specification, root plan, parent phase, and assigned task.
- Executor-result handoffs must not retrieve or write `.work-bundle/knowledge/`.

## Format Guidance

- Small task handoffs should normally be 20-60 lines.
- Medium executor task handoffs should be at most 120 lines; there is no minimum line count.
- Phase and plan result handoffs should normally stay under 180 lines unless real blockers, broad file changes, or many validation results justify more.
- Markdown is allowed only when a real blocker, failure, or broad cross-repository impact cannot be safely represented in sparse YAML.
