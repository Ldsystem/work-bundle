# Task v1 semantic contract

The current `task` family is schema-owned YAML. Supply semantic YAML to `write-task`; the store injects `artifact_type`, `schema_version`, `id`, `plan_id`, `phase_id`, `name`, `status: planned`, `date_created`, and `last_updated` and writes the canonical `.task.yaml` path.

Semantic input requires:

```yaml
order: 1
task_type: implementation
source_ids: [REQ-001A, AC-001]
truth_basis:
  purpose: <bounded outcome>
  as_is_evidence: [<exact current evidence>]
  decision_authority: [none-relevant]
  expected_delta: [<observable result>]
  conflict_status: clear
depends_on: []
source_files: [path/to/source.py]
target_files: [path/to/source.py]
target_symbols: [module.symbol]
interfaces: {consumes: [API-001], produces: []}
steps: [<concrete action>]
validation:
  - id: VAL-001
    kind: process
    command: pytest -q path/to/test.py
    proves: [AC-001]
    expected: passed
    invariant_ids: [INV-001]
    capability_reason: <why this oracle is capable>
evidence_capability:
  result: mapped
  reason: <why validation applies>
  invariants:
    - id: INV-001
      source_ids: [AC-001]
      invariant: <observable claim>
      boundary: component
      oracle: VAL-001
      capability_reason: <why the boundary and oracle are sufficient>
      freshness: current_task_batch
      task_id: task-001
      evidence_ids: [VAL-001]
      closure_result: pending
completion_criteria: [<measurable criterion>]
methodology: {primary: tdd, required_skills: [dev-test-driven-development]}
executor_profile: {capability: judgment, context_mode: compiled-brief, review_capability: judgment}
acceptance_review: {required: false, reviewer_independent: false, verdict: pending, reviewed_head: '', findings: []}
allocated_rules: []
allocated_skills: []
handoff_contract: executor-result-v1
```

`decision_authority` is semantically distinct from generic `source_ids`. Use `none-relevant` only when the verified specification carries no accepted authority, otherwise use its ordered `AUTH-NNN` aliases; the compiler resolves `AUTH-NNN: <carried constraint>`. A conflict status of `escalate` routes `decision-blocked`. `EXC-*`, rejected, deferred, candidate, background, blocked, or superseded authority never enters executor briefs.

Use `no_validation_bearing_obligation` only with a non-empty reason and no invariants. Otherwise every validation-bearing obligation has a task-owned invariant, `capability_reason`, `freshness`, and a capable oracle. Exact suffixed IDs such as `REQ-001A` remain intact.

The compiler validates canonical family, parent bindings, source IDs, dependencies, safe exact scope, structured validation, and authority aliases. It does not decide semantic completeness, appropriate decomposition, evidence sufficiency, or acceptance. Those are direct reviewer judgments against the verified specification and concrete plan tree.

Each task is a coherent bounded execution packet: its source neighborhood, deliverable, capable local validation, review boundary, and repair frontier should let one executor implement and verify the result without unfinished sibling work. A production responsibility may contain several dependency-ordered tasks under one production owner; `depends_on` alone does not prove distinct packets. Keep work together when an intermediate state would be unstable or unreviewable. When ordered tasks reuse a target file, strict dependency order and the predecessor's canonical accepted result are required before successor execution; unordered overlap is rejected. Existing source IDs, interfaces, dependencies, validation, and accepted handoffs express this without a new schema field or contract artifact. A distinct reviewer assesses packet coherence in the existing full-plan or affected-closure review; the controller/orchestrator owns qualification.
