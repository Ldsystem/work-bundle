---
name: orch-create-implementation-plan
description: 'Create executable WorkBundle plans, phases, and tasks from a verified specification when implementation needs dependency, scope, validation, methodology, or delegation structure.'
---

# orch-create-implementation-plan

## Entry gate

Use this skill when a verified specification needs an executable WorkBundle plan tree. Plan only from one canonical active `verified` specification with converged semantics, stable source IDs, resolved material conflicts, explicit knowledge disposition, and coherent current repository evidence. Repair missing specification authority before planning. Do not use this skill for lightweight coding plans or post-execution review/finalization.

Compile only verified authoritative scope. Do not allocate `EXC-*` proposal IDs or rejected, deferred, or not-material excellence proposals as `source_ids`, task scope, or executor briefs. Accepted excellence work enters planning only through the stable requirement, constraint, interface, acceptance-criterion, or validation-target IDs it projected to.

## Canonical output

Author semantic YAML for the `root-plan`, `phase`, and `task` families. Invoke `write-plan`, `write-phase`, and `write-task`; the shared store injects family/schema identity, IDs, qualification/status, dates, and parent bindings and selects `.plan.yaml`, `.phase.yaml`, and `.task.yaml` canonical locations. Do not choose filenames, embed structural overrides, infer parents from directories, or create Markdown compatibility copies.

The root plan binds `source_spec_id`. Every phase binds `plan_id`. Every task binds both `plan_id` and `phase_id`. Use one explicit default phase when no actual barrier or convergence split is needed.

## Planning workflow

1. Use the specification and bounded repository evidence. Add upstream/downstream or validation scope only when current evidence proves it.
2. Do not optimize task or phase cardinality. Decompose only at concrete independently owned production, dependency, validation, review, and repair seams so expected total orchestration cost remains bounded while preserving independently falsifiable increments, short evidence loops, exact dependencies, disjoint write scopes, bounded failure radius, and review boundaries. Assign every authoritative production path to a production owner; reject helper-only allocation while its production path is unowned. Split independently owned entry points only when current repository evidence proves distinct ownership or repair seams. Keep one coherent mechanical increment with one owner, oracle, and repair frontier together. Do not create speculative splits unsupported by current authority, repository, dependency, ownership, validation, or acceptance evidence.
3. Give every task exact source IDs, a five-field Truth Basis, scope, interfaces, dependencies, steps, evidence, methodology, allocated rules/skills, executor profile, and review requirement. Allocate every accepted validation-bearing obligation to a stable `evidence_capability` invariant and the lightest capable task-local oracle. Each entry records source IDs, boundary, oracle, capability reason, freshness, task owner, validation evidence IDs, and initializes `closure_result: pending`. Use `no_validation_bearing_obligation + reason` only when no accepted validation-bearing obligation or design decision exists; never infer it from WOR-61 `none_relevant`.
4. Carry execution-workspace isolation, hydration, and cleanup policy into task and executor context; mutating siblings on the same execution path isolate via prepare_worktree or serialize even when write scopes are disjoint.
5. Use a common contract group before safe parallel work. Contract-decoupled participants depend on the common contract group and accepted prior handoffs, not sibling in-progress implementation output. Create a phase only for an actual barrier or convergence boundary, with explicit barrier ID, readiness evidence, and convergence owner. Cross-branch or joint validation belongs to a post-barrier convergence task.
6. Require a compact `executor-result-v1` handoff. Default `acceptance_review.required: false`. Require task review only when the task sets `acceptance_review.required: true`. Do not infer that flag from soft applicability prose.
7. When a consequential simplification or compatibility assumption exists, make the earliest ordinary task cheaply falsify it before broad edits. Do not add a risk score, checkpoint phase, or parallel lifecycle.
8. When execution proves a task materially under-decomposed, return to the plan and reslice only the affected region around the newly evidenced seam. Preserve the original binding, baseline, and accepted unaffected regions; do not repeatedly enlarge the task.
9. Use the canonical semantic plan projection for review identity and freshness; status-only or append-only evidence changes do not require plan review or reslicing, while authority, scope, dependency, acceptance, decomposition, or validation-allocation changes do.
10. Before initial semantic review, invoke canonical static task admission for every task through the task compiler. After a bounded phase or task repair, rerun admission for the repaired task and any mechanically affected dependency or ownership closure, plus the applicable global collision and graph invariants; do not regenerate unaffected task briefs. Treat schema, family, canonical placement, parent binding, dependency, scope, authority-alias, and validation-shape results as structural facts only. Do not duplicate its predicates in the planner or let it decide semantic completeness.
11. For initial qualification and global root-plan repair, give a distinct reviewer the verified specification, complete canonical plan tree, and bounded current source evidence so coverage, ownership, dependencies, validation, authority, scope, decomposition, and executability are judged directly. For a bounded phase or task repair, the controller/orchestrator identifies the affected semantic authority closure and preserves unaffected qualification. Give the reviewer each complete repaired artifact, applicable root/phase authority, dependency closure, affected interfaces, allocated specification obligations, and bounded source evidence. The reviewer provides advisory `accept`, `repair`, or `blocked` findings; a textual-delta-only check is insufficient, but unrelated plan regions are not rereviewed merely because one artifact changed. The controller/orchestrator assesses that advice and owns impact classification, plan qualification, repair routing, blocking, and continuation. Tests, doctors, indexes, receipts, handoffs, evidence volume, and reviewer advice alone do not issue the qualification decision.
12. Keep planning qualification (`draft`, `verified`, `superseded`) separate from execution state and finalization. Phase/task execution states, handoff/review receipt gates, plan completion, and archive/finalization belong to the downstream execution/review stage.
13. For a bounded existing-task repair, use `amend-task` after returning the root plan to draft. Treat its mechanically affected set as evidence only; the controller/orchestrator decides whether interfaces, ownership, obligation allocation, or shared authority expand the semantic review closure.

Current plan and specification revisions do not consume post-execution review rounds.

## Methodology allocation

```text
semantic artifact              -> dev-semantic-convergence
unexpected behavior            -> dev-systematic-debugging
diagnosed testable repair       -> dev-test-driven-development
new/changed testable behavior   -> dev-test-driven-development
behavior-preserving refactor    -> loop-coding with green characterization baseline
configuration/generated/docs   -> direct with deterministic checks
optional task review (required true) -> dev-code-review
```

## Executor profile

- `mechanical`: one or two files, exact contracts and commands, little judgment.
- `standard`: multi-file coordination, pattern matching, debugging, or integration.
- `judgment`: architecture, concurrency, ambiguous tradeoffs, or high-risk review.

Durable tasks cite `source_ids` and set `context_mode: compiled-brief`; the compiler may duplicate resolved values. Keep provider names out of durable contracts.

## Required task concepts

```yaml
methodology:
  primary: tdd | systematic-debugging | direct | loop-coding
  required_skills: []
executor_profile:
  capability: mechanical | standard | judgment
  context_mode: compiled-brief
  review_capability: standard | judgment
  escalation:
    after_failed_repairs: 2
    next_capability: standard | judgment
acceptance_review:
  required: false
  reviewer_independent: false
  verdict: pending | accept | repair | blocked
  reviewed_head: ""
  findings: []
truth_basis:
  purpose: <bounded outcome>
  as_is_evidence: []
  decision_authority: [none-relevant | <AUTH-NNN alias allocated from verified specification source_knowledge>]
  expected_delta: []
  conflict_status: clear | escalate
```

The compiler resolves each allocated `AUTH-NNN` alias to `AUTH-NNN: <carried constraint>` from verified specification `source_knowledge` without exposing knowledge paths.

Each mapped invariant carries `source_ids`, `boundary`, `oracle`, `capability_reason`, `freshness`, `task_id`, and `evidence_ids`. Task validation entries carry stable `id`, `invariant_ids`, and their own `capability_reason`.

## Semantic convergence

Use `dev-semantic-convergence` with these lenses:

- source-ID coverage;
- non-authoritative excellence exclusion;
- dependencies, task boundaries, and write scopes;
- validation ownership;
- rule, skill, and methodology allocation;
- parallel barrier and convergence safety;
- executor-context completeness.
- evidence-capability completeness, stable source projection, task-local filtering, and lightest-capable boundary selection.

Repair generated drift in the same turn and record compact `semantic_loop` result, round count, and repaired defects. If a source requirement or decision is missing, stop for specification repair.

## Runtime Rules

- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`
- `orch-open-questions`: `rules/orchestration/orch-open-questions.md`
- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-bounded-closure`: `rules/orchestration/orch-bounded-closure.md` when planning or repairing an existing post-execution flow

Central `AGENTS.md` owns rule discovery and loading. Load the runtime rules above when their indexed conditions apply.

## Boundary

Follow `orch-orchestration-boundary`. Do not read durable knowledge directly during downstream execution.

## Self-check

Before returning a plan candidate, confirm from the stored YAML and compiler output that:

- the root plan binds exactly one canonical active verified specification and every phase/task has exact canonical parent bindings;
- repairs updated the current canonical identities in place, the root returned to `draft` before child-content changes, and no intermediate repair copies were retained;
- every accepted specification obligation has explicit phase/task ownership and validation IDs where validation-bearing;
- every authoritative production path has one production owner, exact files/symbols, dependencies, steps, methodology, rules/skills, capable oracle, and measurable completion criteria;
- every phase is justified by an actual barrier or convergence boundary, or the tree uses one explicit default phase;
- static admission passes without legacy Markdown, fallback filenames, broad scans, or a second persisted combined index;
- a distinct reviewer directly assessed the complete current tree for initial/global qualification or the complete affected authority closure for a bounded repair, and the controller/orchestrator evaluated that advice; no textual-delta-only or automatic reviewer verdict qualifies repaired content, while unaffected qualified regions remain valid;
- no task/phase completion, handoff review, receipt, finalization, or archive semantics were added during planning.
