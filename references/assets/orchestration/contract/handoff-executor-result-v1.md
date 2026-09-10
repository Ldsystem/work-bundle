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
lifecycle_authority: location-v1
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
    - id: VAL-001
      invariant_ids: [INV-001]
      command: "exact command"
      result: passed | failed | skipped
      note: "Failure reason or skip reason only."

evidence_closure:
  result: passed | incapable | contradictory | stale | wrong_boundary | failed | missing | unexecuted
  invariants:
    - id: INV-001
      boundary: unit | component | integration | runtime | ui_visual | performance | accessibility | inspection | other
      freshness: current_task_batch
      evidence_ids: [VAL-001]
      closure_result: passed | incapable | contradictory | stale | wrong_boundary | failed | missing | unexecuted
      repair_owner: null | task | plan | specification

knowledge_disposition:
  action: none | update | supersede | reclassify
  reason: "Task-local post-validation evidence."
  affected_authority:
    - AUTH-NNN-or-allocated-source-id-or-task-scope-path

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

defect_closure:
  status: not-applicable | carried-to-review | completed | blocked
  evidence:
    - defect-id-or-path
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
  delegated: true
  owner_kind: subagent
  agent_id: agent-or-provider-identity
  run_id: task-run-identity
  mechanism: host-native | execution-flow

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

- `id`, `type`, `status`, `lifecycle_authority: location-v1`, `project`, `created_at`, `related`, and `result` are always required for newly written handoffs. Embedded `status` is immutable creation metadata; current lifecycle status comes from the status-specific location.
- For a task-scoped executor-result, `related.plan` and `related.task` are required and must equal the assigned task's `plan_id` and `id`. Nested `related.plan` and flat `related_plan` must resolve to exactly one identity. Missing, null, conflicting, or mismatched plan identity fails closed before `Completed` and before `build-review-package` produces a review package. The shared `validate-executor-result` helper owns this gate. Do not infer plan identity from a local task ID.
- `changes.files` is required when files, symbols, artifacts, schemas, commands, or docs changed or were inspected as the task output.
- `validation.commands` is required when any command, test, lint, inspection, or manual verification was run or intentionally skipped.
- `evidence_closure` is required for a completed task whose compiled `evidence_capability.result` is `mapped`. Its invariant IDs, boundary, freshness, and evidence IDs must exactly match allocated task authority. Each referenced validation report carries the allocated `id` and `invariant_ids`; direct harness observation reuses those compiled identities. Only all-`passed` capable, current, correctly bounded evidence closes the task. Negative results fail closed and name the first repair owner: task for failed, stale, or unexecuted implementation evidence; plan for missing, wrong-boundary, or incapable allocation; specification for contradictory accepted authority. Executor-authored closure is corroboration and cannot replace harness observation or semantic review.
- `knowledge_disposition` is required for every completed or partial meaningful move. It records task-local evidence only and does not authorize durable-knowledge retrieval or writes. A change action requires allocated `AUTH-NNN` aliases from the task's accepted decision authority, allocated source IDs, or exact paths already present in the compiled task scope; `none` requires an empty affected-authority list. Invented or unallocated AUTH aliases fail closed.
- `contract_decoupling` is required when a task is marked contract-decoupled or depends on a common contract group.
- `barrier` is required when a task is a barrier participant or convergence owner.
- `convergence` is required when the task owns post-barrier joint debug, integration checks, or cross-branch validation.
- `defect_closure` is required when a review task closes or carries specification-included defect evidence.
- `unresolved` is included only when blockers or issues remain.
- `task_fit_check` is required for completed and partial task results. It records the assigned task, result `clean|repaired|unresolved|skipped`, artifacts checked, and meaningful findings.
- Review requirements come from compiled task authority. Review packets, verdicts, receipts, accepted-result identities, observations, and later audit facts are wrong-owner fields and must not be written into a new executor-result handoff. A structurally complete review-required executor result is admitted before review; accepted-result materialization later joins it with the exact published review and current observations.
- `repository` is required when repository preflight, accepted baseline, changed paths, or blocker state matters for continuation.
- `repository[].metadata` is required when project metadata baseline was used for target resolution, branch checks, commit checks, or CodeGraph policy decisions.
- `codegraph` is required when source-code inspection or edits were in scope. Keep it compact: `root`, `applicable`, `up_to_date`, and required fallback or blocker facts are enough unless a failure needs detail.
- `delegation_evidence` is required for every task executor-result and is optional for non-task scopes. Its five-field closed shape proves mandatory subagent ownership without UI-specific semantics.
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
baseline: {}
acceptance_review: {}
accepted_result: {}
reviewer_run: {}
publication: {}
receipt: {}
```

Use `delegation_evidence` for compact delegation proof. Use `unresolved` and `task_fit_check.findings` for remaining issues instead of `deviations`. Do not include a top-level `baseline`; the helper owns pre-task baseline capture, and executor-result cannot supply or replace that baseline.

## Safety Evidence

Compact handoffs must not weaken safety gates:

- Repository evidence must preserve root, target kind, preflight kind, baseline, and clean or blocked result when applicable.
- Metadata evidence must preserve repository id, expected and actual branch, expected and actual commit, branch status, commit status, and baseline status when project metadata preflight applies.
- CodeGraph evidence must preserve no-index fallback, sync-failed, stale, or blocker facts when applicable.
- Delegation evidence must preserve delegated state, `owner_kind: subagent`, minimum agent/run identity, and `host-native|execution-flow` mechanism. UI, visibility, fallback, controller-owner, and internal-worker fields are invalid.
- Validation evidence must list exact commands or inspections and their result. Executor-authored `result`, `exit_code`, or an equivalently named receipt block is corroboration, not independent proof and not authority for `Completed`. Direct helper observation in the bound worktree is the terminal evidence.
- Task-fit evidence must prove the executor followed the compiled brief and assigned task. Full specification, root-plan, and phase inspection is an escalation path when compiled context is inconsistent.
- Published review authority must identify review independence, the reviewed tree, verdict, and findings outside the executor-result handoff. Accepted-result materialization owns the join and never rewrites the original handoff.
- Executor-result handoffs must not retrieve or write `.work-bundle/knowledge/`.
- `knowledge_disposition.action` is exactly `none`, `update`, `supersede`, or `reclassify`; reasons and affected authority must not name knowledge paths or any `ks-*` skill, and review owns any approved persistence follow-up.
- Contract-decoupled handoffs must show validation against the common contract and accepted prior handoffs, not sibling in-progress implementation.
- Barrier handoffs must show whether the participant reached the barrier or blocked before convergence work is scheduled.
- Defect closure handoffs must use review-owned lifecycle evidence and must not delete defect evidence files.

## Immutable Lifecycle Authority

New handoffs are marked `lifecycle_authority: location-v1`. Their complete bytes never change after creation. The controller moves the same bytes among `active/`, `reviewed/`, `superseded/`, and `archived/`; the index derives current status from that location and lookups search every status directory. Same-state requests are no-ops and write neither artifact, override, index, nor dispatch evidence.

Unmarked historical handoffs are not rewritten or bulk-migrated. Without an override, an unmarked file in `active/` uses a recognized embedded status and an unmarked file in a non-active status directory uses its location. On the first actual explicit status change, including return to `active`, the controller writes only `handoff/legacy-status-overrides/<handoff-id>.json`, binding the complete-byte digest, type, related plan/task, and current status. A valid override then takes precedence and must agree with location. Duplicate identities, type/folder disagreement, task/plan contradictions, or override digest/binding/location contradictions fail closed.

## Format Guidance

- Small task handoffs should normally be 20-60 lines.
- Medium executor task handoffs should be at most 120 lines; there is no minimum line count.
- Phase and plan result handoffs should normally stay under 180 lines unless real blockers, broad file changes, or many validation results justify more.
- Markdown is allowed only when a real blocker, failure, or broad cross-repository impact cannot be safely represented in sparse YAML.
