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
- For an accepted-invariant `execution_introduced_bug` or `implementation_gap`, require `invariant_trace` to connect original requirement, specification invariant, owning plan task or acceptance criterion, changed commit, materialization, and runtime or UI proof. Passing component or unit tests alone is insufficient for this triggered runtime claim; do not impose a universal browser or UI gate when neither trigger applies.
- Permit `new_feature` or `uncovered_fixture` with an empty `invariant_trace` only when `negative_evidence` proves no matching original user request or accepted specification invariant and no plan, handoff, or produced-commit contradiction.
- Route `owning_repair` to the first broken artifact: task or acceptance criterion present plus implementation miss means task repair and re-review; accepted specification present plus plan omission means plan repair and resume from the owning step; original-request invariant omitted or contradicted by the accepted specification means specification repair. Only after those cases are excluded may a residual class stand.
- Keep classification agent-owned and evidence-linked. A helper may require and structurally validate the record but must not decide the semantic class.

## Must Not

- Do not broadly inspect project source to redo task code review.
- Do not reread implementation source for code quality.
- Do not start another implementation-review agent for plan-level acceptance.
- Do not repair implementation or test code during final review.
- Do not substitute project-file inspection for accepted task-review evidence on tasks that explicitly required review.
- Do not create a repair specification for every failed review gate.
- Do not archive while required knowledge, validation, review, repository, or workspace evidence is unresolved.
- Do not directly write durable knowledge from orchestration.

## Validation

- Confirm every completed review-required task has fresh validation, a valid executor-result handoff, and `accept` review evidence.
- Confirm missing `acceptance_review.verdict` is not a blocker unless the task explicitly required review.
- Confirm declared completion evidence matches the compiled Truth Basis, source IDs, and AUTH constraints.
- Confirm blocker routing names the owning resume path instead of restarting the lifecycle.
- Confirm finalization and archive occur only after knowledge disposition and deterministic gates resolve.

## On Violation

Stop finalization, emit the smallest typed blocker, and resume the step that owns the missing or contradictory evidence. Repair a plan or specification only when the defect belongs to that artifact.
