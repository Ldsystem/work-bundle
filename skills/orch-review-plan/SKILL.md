---
name: orch-review-plan
description: 'Audit WorkBundle workflow completion, task acceptance evidence, handoffs, knowledge disposition, repository finalization, and archive readiness after execution.'
---

# orch-review-plan

## Review question

Did the approved WorkBundle workflow complete correctly, with required task acceptance evidence, handoffs, knowledge disposition, repository finalization, and archive readiness?

This is a workflow audit and deterministic finalizer. Independent `dev-code-review` owns task-scoped implementation quality before task completion.

## Audit

Verify:

- specification, plan, phase, and task status coherence;
- executor-result handoffs by applicability;
- `acceptance_review.verdict: accept` wherever review was required;
- accepted Truth Basis, implementation evidence, test oracle, and task-local knowledge disposition agree in each accepted review package;
- planned validation evidence exists and is fresh for the accepted task result;
- declared dependency, barrier, and convergence gates occurred;
- Knowledge Base Update disposition is `completed` or `not-needed` before archive;
- approved `ks-*` return evidence exists when durable knowledge was required;
- allowed commit, applicable CodeGraph sync, metadata update, archive, and index refresh completed or are explicitly not applicable.

Use project files only for bounded identity and finalization evidence. Do not broadly inspect source to decide code quality, redo task review, repair source/tests, or substitute file inspection for accepted review evidence.

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

When disposition is `required`, invoke the approved keep-summarizing owner with accepted implementation, validation, handoff, review, and decision evidence. Review owns approved persistence delegation; executor disposition evidence never invokes a `ks-*` skill. Validate structural-value result, written or updated durable paths or evidence-backed no-write rationale, index rebuild status, blockers, and completion state. Resume only from that return evidence. Orchestration does not directly create, edit, promote, delete, or index durable knowledge.

## Finalization

Keep audit judgment and deterministic finalization together in this skill for now; do not create `orch-finalize-plan`. After every audit gate passes, invoke the smallest existing helper for allowed commit, CodeGraph sync, project metadata update, archive, and index refresh. Clean only a WorkBundle-owned execution workspace when policy and proven Git identity allow it.

Archive remains blocked while any required knowledge, validation, review, handoff, repository, workspace, or unsettled decision evidence is incomplete or contradictory.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-review-completion`: `rules/orchestration/orch-review-completion.md`

Central `AGENTS.md` owns rule discovery and loading. Load the runtime rules above when their indexed conditions apply.

## Boundary

Follow `orch-orchestration-boundary` and `orch-review-completion`.
