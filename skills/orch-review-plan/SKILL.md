---
name: orch-review-plan
description: 'Audit WorkBundle workflow completion, task acceptance evidence, handoffs, knowledge disposition, repository finalization, and archive readiness after execution.'
---

# orch-review-plan

## Review question

Did the approved WorkBundle workflow complete correctly, with required optional reviews, declared plan-level/integration acceptance, handoffs, knowledge disposition, repository finalization, and archive readiness?

This is a workflow audit and deterministic finalizer. Independent `dev-code-review` owns task-scoped implementation quality when review is explicitly required.

The audit has no mandatory Execution Flow dependency: host-native execution is sufficient and Execution Flow is optional.

## Audit

Verify:

- specification, plan, phase, and task status coherence;
- executor-result handoffs by applicability;
- declared completion evidence corresponds to the compiled Truth Basis, source IDs, expected delta, and remaining AUTH constraints;
- every mapped invariant has capable, current, correctly bounded harness-observed evidence under its allocated INV/VAL identities; treat incapable green, contradiction, staleness, wrong-boundary, failure, missing, or unexecuted evidence as negative acceptance evidence and route first-owner repair: task repair for failed, stale, or unexecuted implementation evidence; plan repair for missing, wrong-boundary, or incapable allocation; specification repair for contradictory accepted authority;
- missing stored `accept` review authority blocks only a task whose compiled `review_required` is true; do not require universal task-review evidence or embedded handoff verdicts;
- exact stored `accept` authority only for those explicitly required reviews, joined during accepted-result materialization;
- declared plan-level/integration acceptance observed on the final integrated workspace; do not start another implementation-review agent to produce plan-level acceptance;
- aggregate accepted task dispositions before applying the final knowledge gate: any accepted `update`, `supersede`, or `reclassify` makes durable closure required even when the upstream specification said `not-needed`; accepted `none` and rejected task dispositions do not trigger closure;
- record validated delegate-return state in the root plan's existing Knowledge Base Update `Closure return` field so the deterministic `archive-plan` helper enforces the same aggregate gate;
- planned validation evidence exists and is fresh for the accepted task result;
- declared dependency, barrier, and convergence gates occurred;
- the resulting final Knowledge Base Update disposition is `completed` or `not-needed` before archive;
- approved `ks-*` return evidence exists when durable knowledge was required;
- allowed commit, applicable CodeGraph sync, metadata update, archive, and index refresh completed or are explicitly not applicable.
- dependency, finalization, resume, and archive decisions consume compact accepted results and current harness observations without replaying transient evidence or historical handoff chains.
- required task and stage verdicts are strongly checked with provider-specific reviewer-run receipts at publication, then later admitted from immutable direct current-authority bindings and still-current targets without receipt or predecessor replay; bare output, unattached receipts, and bare findings are not lifecycle authority.
- product findings concern accepted product requirements/boundaries, exact product source/diff, normalized harness observations, and unresolved product concerns; handoff, knowledge disposition, reviewer history, and publication/status/archive bookkeeping stay with controller audit.

## Evidence capability correspondence

Before archive or completion, every accepted validation-bearing invariant must have a compiled `evidence_capability` entry and capable, current, correctly bounded harness-observed evidence under its allocated INV/VAL identities. Incapable green, contradiction, staleness, wrong-boundary, failure, missing, or unexecuted evidence is negative acceptance evidence, not closure.

Use `no_validation_bearing_obligation + reason` only when no accepted validation-bearing obligation or design decision exists. Do not infer an empty evidence-capability map from a WOR-61 `none_relevant` impact result.

Route first-owner repair for this pre-closure oracle-capability check: task repair for failed, stale, or unexecuted implementation evidence; plan repair for missing, wrong-boundary, or incapable allocation; specification repair for contradictory accepted authority. Mechanical helpers validate IDs, completeness, provenance, and observed results; agents own semantic capability judgment. This is not a universal browser, E2E, production, or runtime gate.

Keep this pre-closure oracle-capability check distinct from `RuntimeVerificationClassificationV1`. WOR-59 G9 remains the unchanged post-execution classifier and may use this map only as evidence when triggered.

## Runtime verification classification

When a runtime or UI defect is reported after execution, or an accepted specification or plan explicitly claims runtime acceptance of a user-visible invariant, record a `RuntimeVerificationClassificationV1` before archive or residual feature routing. Review the authority chain in order: original user request and accepted specification; compiled plan and task acceptance criteria; executor handoffs and produced commits; then execution-introduced behavior.

The record contains `classification`, `invariant_trace`, `negative_evidence`, and `owning_repair`. `classification` is one of `execution_introduced_bug`, `implementation_gap`, `new_feature`, or `uncovered_fixture`. For `execution_introduced_bug` and `implementation_gap` tied to an accepted invariant, `invariant_trace` must connect original requirement, specification invariant, owning plan task or acceptance criterion, changed commit, materialization, presentation, and runtime or UI proof. Passing component or unit tests alone is insufficient for this triggered runtime claim. This is not a universal browser or UI gate for plans without either trigger.

`new_feature` or `uncovered_fixture` may have an empty `invariant_trace` only when `negative_evidence` records no matching original request or accepted specification invariant and no contradiction in the plan, handoff, or produced commit. Route `owning_repair` to the first broken artifact: an invariant already present in the task or acceptance criterion requires task repair and re-review; a specification invariant omitted from plan decomposition requires plan repair and resume from the owning step; an original-request invariant omitted or contradicted by the specification requires specification repair. Only after those routes are excluded may a residual class stand.

Classification remains agent-owned and evidence-linked. A helper may require the record and validate its structure, but must not decide the semantic class. This audit must not expand into a broad source-quality reread or create another implementation-review agent.

Keep same-scope specification-owned handling authoritative for a first-observed classification defect. Persist separate WorkBundle defect evidence only after `wb-defect-evaluation` classifies the finding as work-bundle-scoped or mixed and same-scope specification-owned handling no longer applies.

Use project files only for bounded identity and finalization evidence. Do not broadly inspect source to decide code quality, redo task review, reread implementation for code quality, repair source/tests, or start another implementation-review agent for plan-level acceptance.

## Typed routing

```text
missing initial executor handoff
  -> review-blocked -> resume initial result owner
accepted-task source repair
  -> existing task owner -> claim-relevant validation -> scoped rereview
publication/status/archive control failure
  -> controller owner -> reuse compact accepted result and completed review
knowledge work or return evidence incomplete
  -> knowledge-blocked -> resume approved ks-* delegate-return path
metadata/index/repository finalization incomplete
  -> repository-blocked -> bounded deterministic helper
workspace preparation/cleanup/finalization incomplete
  -> workspace-blocked -> bounded execution-workspace helper
implementation rejected
  -> task repair and independent re-review
failed, stale, or unexecuted implementation evidence
  -> task repair
incapable, missing, or wrong-boundary allocation
  -> plan repair
contradictory accepted authority
  -> specification repair
plan decomposition defect
  -> repair plan only
requirement/design/authority defect
  -> repair specification
```

Do not create a repair specification for every failed gate.

## Knowledge delegate-return

When the upstream disposition or aggregate accepted task dispositions make closure `required`, invoke the approved keep-summarizing owner with accepted implementation, validation, handoff, review, and decision evidence. Review owns approved persistence delegation; executor disposition evidence never invokes a `ks-*` skill. Validate structural-value result, written or updated durable paths or evidence-backed no-write rationale, index rebuild status, blockers, and completion state. Resume only from that return evidence. Orchestration does not directly create, edit, promote, delete, or index durable knowledge, and archive remains blocked until the validated return resolves required closure.

Knowledge closure gates final completion and archive; it never precedes specification, plan, task, or integrated-implementation review.

## Finalization

Keep audit judgment and deterministic finalization together in this skill for now; do not create `orch-finalize-plan`. After every audit gate passes, invoke the smallest existing helper for allowed commit, CodeGraph sync, project metadata update, archive, and index refresh. Clean only a WorkBundle-owned execution workspace when policy and proven Git identity allow it.

For post-execution integrated review, first confirm every executor attempt is terminal, then call `begin-review-round` before evidence preparation or reviewer dispatch. Complete the reserved round with `complete-review-round` using the immutable stored product review reference, or a factual controller audit-block when no product review artifact exists. The audit-block records controller failure only and must not impersonate a product verdict. Use `review-round-status` to report the current frozen target, completed count, finalization requirement, and blocker route.

An accepted post-execution review round follows the normal final audit, knowledge, repository, archive, and index gates above. Findings below the fifth completed round route to scoped repair. The fifth unresolved or blocked round routes to `finalize-with-blockers`: persist finalization-required state, validate the residual specification and clean source baselines, persist the active workspace blocker, validate and record the review-owned knowledge return, archive the origin specification and plan and update their indexes without collision overwrite, release owned bindings, and persist terminal closure. Retry an incomplete administrative stage without reopening product work or rerunning review.

Archive remains blocked while any required knowledge, validation, review, handoff, repository, workspace, or unsettled decision evidence is incomplete or contradictory.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-review-completion`: `rules/orchestration/orch-review-completion.md`
- `orch-bounded-closure`: `rules/orchestration/orch-bounded-closure.md`

Central `AGENTS.md` owns rule discovery and loading. Load the runtime rules above when their indexed conditions apply.

## Boundary

Follow `orch-orchestration-boundary`, `orch-review-completion`, and `orch-bounded-closure`.
