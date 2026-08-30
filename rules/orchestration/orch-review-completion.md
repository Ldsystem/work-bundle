---
id: orch-review-completion
applies_when:
  - review-plan audits a completed or blocked implementation plan
  - orchestration artifacts may be finalized or archived
enforcement: must
load: conditional
requires: []
---

# Orchestration Review Completion

## Purpose

Keep final review focused on whether the WorkBundle workflow completed correctly. Independent task review is optional and owns task-scoped implementation quality only when a task explicitly required it.

## Must

- Confirm each required task review compared the accepted Truth Basis, implementation, test oracle, and task-local knowledge disposition before accepting the task.
- Check that declared completion evidence corresponds to the compiled Truth Basis, source IDs, expected delta, and remaining AUTH constraints.
- Before archive or completion, confirm every accepted validation-bearing invariant has a compiled `evidence_capability` entry and capable, current, correctly bounded harness-observed evidence under its allocated INV/VAL identities. Treat incapable green, contradiction, staleness, wrong-boundary, failure, missing, or unexecuted evidence as negative acceptance evidence, not closure.
- Use `no_validation_bearing_obligation + reason` only when no accepted validation-bearing obligation or design decision exists. Do not infer an empty evidence-capability map from a WOR-61 `none_relevant` impact result.
- Route first-owner repair for this pre-closure oracle-capability check: task repair for failed, stale, or unexecuted implementation evidence; plan repair for missing, wrong-boundary, or incapable allocation; specification repair for contradictory accepted authority.
- Keep this pre-closure oracle-capability check distinct from `RuntimeVerificationClassificationV1`. WOR-59 G9 remains the unchanged post-execution classifier and may use this map only as evidence when triggered. Mechanical helpers validate IDs, completeness, provenance, and observed results; agents own semantic capability judgment and must not impose a universal browser, E2E, production, or runtime gate.
- Missing `acceptance_review.verdict` blocks only a task that explicitly required independent review. Do not require universal task-review evidence.
- Keep approved `ks-*` persistence delegation review-owned; executor disposition evidence never authorizes knowledge retrieval or writes.

- Audit spec, plan, phase, task, handoff, and required optional-review status coherence.
- Require fresh planned validation evidence and an `accept` task-review verdict wherever review is explicitly required.
- Verify declared dependency, barrier, and convergence gates from recorded evidence.
- Use declared plan-level/integration acceptance from recorded validation; do not start another implementation-review agent to produce plan-level acceptance.
- Aggregate only accepted task dispositions. Any accepted `update`, `supersede`, or `reclassify` promotes final durable closure to `required` even when the upstream specification says `not-needed`; accepted `none` and rejected dispositions do not trigger closure.
- Route missing handoff, status, validation, or review evidence to `review-blocked` and resume the owning execution step.
- Route incomplete durable knowledge work to `knowledge-blocked` and resume the approved `ks-*` delegate-return path.
- Route incomplete repository metadata, index, workspace, or archive mechanics to `repository-blocked` or `workspace-blocked` and use bounded deterministic helpers.
- Require the execution-evidence-driven final Knowledge Base Update disposition to be `completed` or `not-needed` before archive; archive remains blocked while promoted closure lacks validated keep-summarizing return evidence.
- Create or require plan repair only for a decomposition defect, and specification repair only for a requirement, design, or authority defect.
- Complete allowed commit, applicable CodeGraph sync, metadata update, archive, and index refresh only after all gates allow finalization.
- When a post-execution runtime or UI defect is classified, or the accepted specification or plan explicitly claims runtime acceptance of a user-visible invariant, require a `RuntimeVerificationClassificationV1` before archive. Evaluate the original user request and accepted specification before the plan, task acceptance criteria, executor handoffs, produced commits, and execution-introduced behavior.
- Require `RuntimeVerificationClassificationV1` to carry `classification`, `invariant_trace`, `negative_evidence`, and `owning_repair`. Accepted classes are `execution_introduced_bug`, `implementation_gap`, `new_feature`, and `uncovered_fixture`.
- For an accepted-invariant `execution_introduced_bug` or `implementation_gap`, require `invariant_trace` to connect original requirement, specification invariant, owning plan task or acceptance criterion, changed commit, materialization, presentation, and runtime or UI proof. Passing component or unit tests alone is insufficient for this triggered runtime claim; do not impose a universal browser or UI gate when neither trigger applies.
- Permit `new_feature` or `uncovered_fixture` with an empty `invariant_trace` only when `negative_evidence` proves no matching original user request or accepted specification invariant and no plan, handoff, or produced-commit contradiction.
- Route `owning_repair` to the first broken artifact: task or acceptance criterion present plus implementation miss means task repair and re-review; accepted specification present plus plan omission means plan repair and resume from the owning step; original-request invariant omitted or contradicted by the accepted specification means specification repair. Only after those cases are excluded may a residual class stand.
- Keep classification agent-owned and evidence-linked. A helper may require and structurally validate the record but must not decide the semantic class.
- Keep same-scope specification-owned handling authoritative for a first-observed classification defect. Persist separate WorkBundle defect evidence only after `wb-defect-evaluation` classifies the finding as work-bundle-scoped or mixed and same-scope specification-owned handling no longer applies.

## Must Not

- Do not broadly inspect project source to redo task code review.
- Do not reread implementation source for code quality.
- Do not start another implementation-review agent for plan-level acceptance.
- Do not repair implementation or test code during final review.
- Do not substitute project-file inspection for accepted task-review evidence on tasks that explicitly required review.
- Do not create a repair specification for every failed review gate.
- Do not archive while required knowledge, validation, review, repository, or workspace evidence is unresolved.
- Do not close an invariant on a green oracle that cannot observe it or that contradicts accepted authority.
- Do not treat WOR-59 G9 classification as this pre-closure oracle-capability check, or replace G9 with it.
- Do not infer an empty evidence-capability map from a WOR-61 `none_relevant` impact result.
- Do not impose a universal browser, E2E, production, or runtime gate.
- Do not directly write durable knowledge from orchestration.

## Validation

- Confirm every completed review-required task has fresh validation, a valid executor-result handoff, and `accept` review evidence.
- Confirm missing `acceptance_review.verdict` is not a blocker unless the task explicitly required review.
- Confirm declared completion evidence matches the compiled Truth Basis, source IDs, and AUTH constraints.
- Confirm every mapped invariant has capable, current, correctly bounded harness-observed evidence under its allocated INV/VAL identities, or a typed first-owner repair route; confirm `no_validation_bearing_obligation` is not inferred from WOR-61 `none_relevant`.
- Confirm this pre-closure oracle-capability check remains distinct from `RuntimeVerificationClassificationV1` and that WOR-59 G9 remains the unchanged post-execution classifier.
- Confirm blocker routing names the owning resume path instead of restarting the lifecycle.
- Confirm finalization and archive occur only after knowledge disposition and deterministic gates resolve.

## On Violation

Stop finalization, emit the smallest typed blocker, and resume the step that owns the missing or contradictory evidence. Repair a plan or specification only when the defect belongs to that artifact.
