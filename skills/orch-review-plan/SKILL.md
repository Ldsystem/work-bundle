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
