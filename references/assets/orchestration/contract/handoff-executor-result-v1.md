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

knowledge_disposition:
  action: none | update | supersede | reclassify
  reason: "Task-local post-validation evidence."
  affected_authority:
    - source-id-or-authority-path

contract_decoupling:
  common_contract_group: CG-001
  common_contract_paths:
    - path/to/contract.md
  validation_scope:
    - common-contract
    - accepted-prior-handoffs
    - task-local-files
  forbidden_peer_validation: respected | violated | not-applicable
  note: "Only include when needed."

barrier:
  id: BAR-001
  role: participant | convergence-owner
  readiness: reached | blocked | not-applicable
  participants_complete_or_blocked: true | false | null
  note: "Only include when needed."

convergence:
  owner: task-id-or-null
  status: ready | completed | blocked | not-applicable
  checks:
    - "exact command or inspection"

violation_closure:
  status: not-applicable | carried-to-review | completed | blocked
  evidence:
    - violation-id-or-path
  note: "Review-only closure evidence; executors do not delete evidence."

unresolved:
  - "Only include blockers or issues that remain."

task_fit_check:
  task: path-or-id
  result: clean | repaired | unresolved | skipped
  artifacts_checked:
    - compiled task brief
    - assigned task
  findings: []

acceptance_review:
  required: true | false
  reviewer_independent: true | false
  verdict: pending | accept | repair | blocked
  reviewed_head: commit-or-tree-identity
  findings:
    - severity: blocking | advisory
      scope: specification | correctness | quality | validation | rule
      finding: "Compact evidence-backed text."

repository:
  - root: /absolute/path
    target_kind: git-backed | local-project
    preflight_kind: git-clean-worktree | local-project
    baseline: initial | accepted-handoff
    status: clean | blocked
    metadata:
      repository_id: null
      expected_branch: null
      actual_branch: null
      branch_status: matched | mismatch | not-applicable | unknown
      expected_commit: null
      actual_commit: null
      commit_status: matched | stale | missing | unborn | not-applicable | unknown
      baseline_status: current | stale | unborn | not-git | unknown

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

allocation_evidence:
  allocated_rules:
    - id: rule-id
      status: loaded | condition-evaluated | skipped | unavailable
      reason: null
  allocated_skills:
    - name: skill-name
      status: used | acknowledged | skipped | unavailable
      reason: null
```

## Required By Applicability

- `id`, `type`, `status`, `project`, `created_at`, `related`, and `result` are always required.
- `changes.files` is required when files, symbols, artifacts, schemas, commands, or docs changed or were inspected as the task output.
- `validation.commands` is required when any command, test, lint, inspection, or manual verification was run or intentionally skipped.
- `knowledge_disposition` is required for every completed or partial meaningful move. It records task-local evidence only and does not authorize durable-knowledge retrieval or writes. A change action requires affected authority drawn from allocated source IDs or task-local paths; `none` requires an empty affected-authority list.
- `contract_decoupling` is required when a task is marked contract-decoupled or depends on a common contract group.
- `barrier` is required when a task is a barrier participant or convergence owner.
- `convergence` is required when the task owns post-barrier joint debug, integration checks, or cross-branch validation.
- `violation_closure` is required when a review task closes or carries specification-included violation evidence.
- `unresolved` is included only when blockers or issues remain.
- `task_fit_check` is required for completed and partial task results. It records the assigned task, result `clean|repaired|unresolved|skipped`, artifacts checked, and meaningful findings.
- `acceptance_review` is required when the task contract requires review. A review-required task cannot become `Completed` until the verdict is `accept`.
- `repository` is required when repository preflight, accepted baseline, changed paths, or blocker state matters for continuation.
- `repository[].metadata` is required when project metadata baseline was used for target resolution, branch checks, commit checks, or CodeGraph policy decisions.
- `codegraph` is required when source-code inspection or edits were in scope. Keep it compact: `root`, `applicable`, `up_to_date`, and required fallback or blocker facts are enough unless a failure needs detail.
- `delegation_evidence` is required when task, phase, or plan ownership was delegated or when the execution path needs proof that invisible internal spawn did not own delegation.
- `allocation_evidence` is required when allocated_rules or allocated_skills materially shaped execution or when an allocated rule/skill was unavailable, skipped, stale, or inapplicable.

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
- Metadata evidence must preserve repository id, expected and actual branch, expected and actual commit, branch status, commit status, and baseline status when project metadata preflight applies.
- CodeGraph evidence must preserve no-index fallback, sync-failed, stale, or blocker facts when applicable.
- Delegation evidence must preserve visible surface, visible reference when available, and `internal_spawn_used_for_task_delegation: false`.
- Validation evidence must list exact commands or inspections and their result.
- Task-fit evidence must prove the executor followed the compiled brief and assigned task. Full specification, root-plan, and phase inspection is an escalation path when compiled context is inconsistent.
- Acceptance-review evidence must identify review independence, the reviewed tree, verdict, and blocking or advisory findings.
- Executor-result handoffs must not retrieve or write `.work-bundle/knowledge/`.
- `knowledge_disposition.action` is exactly `none`, `update`, `supersede`, or `reclassify`; reasons and affected authority must not name knowledge paths or persistence skills, and review owns any approved persistence follow-up.
- Contract-decoupled handoffs must show validation against the common contract and accepted prior handoffs, not sibling in-progress implementation.
- Barrier handoffs must show whether the participant reached the barrier or blocked before convergence work is scheduled.
- Violation closure handoffs must use review-owned lifecycle evidence and must not delete violation evidence files.

## Format Guidance

- Small task handoffs should normally be 20-60 lines.
- Medium executor task handoffs should be at most 120 lines; there is no minimum line count.
- Phase and plan result handoffs should normally stay under 180 lines unless real blockers, broad file changes, or many validation results justify more.
- Markdown is allowed only when a real blocker, failure, or broad cross-repository impact cannot be safely represented in sparse YAML.
