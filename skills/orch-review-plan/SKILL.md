---
name: orch-review-plan
description: 'Audit WorkBundle workflow completion, task acceptance evidence, handoffs, knowledge disposition, repository finalization, and archive readiness after execution.'
---

# orch-review-plan

## Review question

Did the approved WorkBundle workflow complete correctly, with required optional reviews, declared plan-level/integration acceptance, handoffs, knowledge disposition, repository finalization, and archive readiness?

This is a workflow audit and deterministic finalizer. Independent `dev-code-review` owns task-scoped implementation quality when review is explicitly required.

## Audit

Verify:

- specification, plan, phase, and task status coherence;
- executor-result handoffs by applicability;
- declared completion evidence corresponds to the compiled Truth Basis, source IDs, expected delta, and remaining AUTH constraints;
- every mapped invariant has capable, current, correctly bounded harness-observed evidence under its allocated INV/VAL identities; treat incapable green, contradiction, staleness, wrong-boundary, failure, missing, or unexecuted evidence as negative acceptance evidence and route first-owner repair: task repair for failed, stale, or unexecuted implementation evidence; plan repair for missing, wrong-boundary, or incapable allocation; specification repair for contradictory accepted authority;
- missing `acceptance_review.verdict` blocks only a task that explicitly required independent review; do not require universal task-review evidence;
- `acceptance_review.verdict: accept` only for those explicitly required reviews;
- declared plan-level/integration acceptance observed on the final integrated workspace; do not start another implementation-review agent to produce plan-level acceptance;
- aggregate accepted task dispositions before applying the final knowledge gate: any accepted `update`, `supersede`, or `reclassify` makes durable closure required even when the upstream specification said `not-needed`; accepted `none` and rejected task dispositions do not trigger closure;
- record validated delegate-return state in the root plan's existing Knowledge Base Update `Closure return` field so the deterministic `archive-plan` helper enforces the same aggregate gate;
- planned validation evidence exists and is fresh for the accepted task result;
- declared dependency, barrier, and convergence gates occurred;
- the resulting final Knowledge Base Update disposition is `completed` or `not-needed` before archive;
- approved `ks-*` return evidence exists when durable knowledge was required;
- allowed commit, applicable CodeGraph sync, metadata update, archive, and index refresh completed or are explicitly not applicable.

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

Keep same-scope specification-owned handling authoritative for a first-observed classification defect. Persist separate WorkBundle violation evidence only after `wb-violation-evaluation` classifies the finding as work-bundle-scoped or mixed and same-scope specification-owned handling no longer applies.

Use project files only for bounded identity and finalization evidence. Do not broadly inspect source to decide code quality, redo task review, reread implementation for code quality, repair source/tests, or start another implementation-review agent for plan-level acceptance.

## Typed routing

```text
missing handoff/status/validation/review evidence
  -> review-blocked -> resume owning execution step
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

## Finalization

Keep audit judgment and deterministic finalization together in this skill for now; do not create `orch-finalize-plan`. After every audit gate passes, invoke the smallest existing helper for allowed commit, CodeGraph sync, project metadata update, archive, and index refresh. Clean only a WorkBundle-owned execution workspace when policy and proven Git identity allow it.

Archive remains blocked while any required knowledge, validation, review, handoff, repository, workspace, or unsettled decision evidence is incomplete or contradictory.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-review-completion`: `rules/orchestration/orch-review-completion.md`

Central `AGENTS.md` owns rule discovery and loading. Load the runtime rules above when their indexed conditions apply.

## Boundary

Follow `orch-orchestration-boundary` and `orch-review-completion`.
