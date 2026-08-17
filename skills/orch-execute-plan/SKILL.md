---
name: orch-execute-plan
description: 'Execute a WorkBundle task, phase, or plan through compiled task briefs, task-local methodology, optional independent acceptance review, and dependency-aware scheduling.'
---

# orch-execute-plan

## Execution Constraints (skill-owned)

Execution is a no-retrieval stage. Use the selected task, its compiled Truth Basis and cited specification values, declared prior handoffs, task-scoped source/tests, and allocated methodology. Do not query or read `.work-bundle/knowledge/`.

## Scheduler-Owned Constraints

1. Resolve target task, phase, or plan and its executable dependency queue.
2. Before compilation, capability selection, delegation, or edits, resolve the workspace and every target repository from `.work-bundle/project.yaml`. Git-backed targets must match branch and accepted metadata baseline and be clean unless validated handoffs explain exact changes. Never mutate user work to pass preflight.
3. Record CodeGraph applicability per target. When `.codegraph/` exists for indexed source work, sync after preflight and query it before broad inspection; recheck cleanliness and sync after changes. Otherwise record `no-index` and use bounded direct inspection. Do not initialize CodeGraph.
4. Select or prepare the declared execution workspace and hydration profile. Record provenance. Cleanup may remove only a clean WorkBundle-owned workspace whose expected Git identity still matches, whose policy allows cleanup, and whose durable lifecycle state confirms integration or an explicit discarded/retired decision. Age alone is report-only; never delete user or harness workspaces.
5. After scheduler workspace selection or preparation and before material edits, create or load one harness-owned task execution binding that carries plan/task identity, `workspace_id`/`execution_id`/`repository_id`, and exact path/Git provenance. Keep it in runtime/execution-workspace state outside the mutation envelope. Compile and read task/spec artifacts from the control WorkBundle root. Execute process and Git evidence against the bound execution repository. Do not point orchestration `--project-root` at an isolated worktree to load gitignored `.work-bundle/orchestration/**`. Capture the pre-task baseline once from that bound repository; later brief rebuild or repair must not recapture or replace it. Mutating siblings on the same execution path isolate via prepare_worktree or serialize even when write scopes are disjoint; a shared worktree must not host them. Do not add a path-ownership ledger.
6. Compile the bounded task brief:

```bash
python3 scripts/orch.py build-task-brief --task <task-path>
```

Missing source IDs; decision authority other than `none-relevant` or an `AUTH-NNN` alias whose carried constraint was reconciled in the verified specification; `conflict_status: escalate`; inconsistent scope; or unsafe workspace state fails closed with the existing typed blocker. Truth Basis conflict uses `decision-blocked`. The compiled brief includes `AUTH-NNN: <carried constraint>`, not the alias alone.
7. Choose the provider-neutral capability from the task profile. Partition only independent tasks with disjoint write scopes. Contract-decoupled participants validate against the common contract, accepted prior handoffs, and task-local files; they reach the named barrier before convergence work.
8. When user/environment policy permits delegation, use visible multi-agent subagents for task ownership. Invisible helper workers may support bounded analysis only. If independent subagents are unavailable, use single-agent execution and mark later review `reviewer_independent: false`.
9. Always validate the executor-result with the shared helper. The helper observes required process/inspection items in the bound worktree as one Git-state-neutral batch, then authorizes from post-execution task-caused delta. Compile `build-review-package` and assign `dev-code-review` only when `acceptance_review.required: true` or compiled `review_required: true`. The scheduler does not perform code-quality review.

```bash
python3 scripts/orch.py validate-executor-result --task <task-path> --handoff <handoff-path>
```

## Executor-Owned Constraints

- Follow the compiled brief and its exact read/write/forbidden scope.
- Load or acknowledge allocated rules and methodology before the operation they govern.
- Create or load the harness-owned task execution binding before material edits; capture the pre-task baseline once; run process commands and named inspections only in the bound execution repository.
- Apply `systematic-debugging` before proposing a root-cause fix for unexpected behavior.
- Apply TDD to testable new/changed behavior and diagnosed fixes; use direct deterministic verification for non-testable mechanical artifacts.
- Run fresh claim-relevant validation after the final edit.
- Write a sparse `executor-result-v1` handoff containing task identity, changed paths, validation, repository/CodeGraph fallback, allocated obligations, unresolved blockers, local task-fit evidence, and a knowledge disposition of `none`, `update`, `supersede`, or `reclassify`.
- Knowledge disposition contains task-local evidence only. It must not name knowledge paths, invoke any `ks-*` skill, or authorize persistence; final orchestration review owns approved follow-up.
- Do not perform acceptance judgment or mark a review-required task complete.
- Trigger `wb-violation-evaluation` only for a new unintended WorkBundle-related conflict, error, failed validation, or contradictory workflow behavior. Stop once visible relatedness is established; no chain-of-thought or exhaustive tracing is required.

## Independent task review

When `acceptance_review.required: true` or `review_required: true`, build the package from the task, handoff, and original base/current head. Skip this hop when review is not required.

```bash
python3 scripts/orch.py build-review-package \
  --task <task-path> --handoff <handoff-path> --base <git-ref> --head <git-ref>
```

Use `--head worktree` for pre-commit review; the compiler includes tracked, staged, unstaged, and untracked changes, assigns a stable worktree identity, and withholds protected-path content.

The reviewer uses only the bounded package and `dev-code-review`. It compares the accepted Truth Basis, implementation, test oracle, and knowledge disposition, then returns `accept`, `repair`, or `blocked` with the reviewed tree identity and compact evidence-backed findings.

On `repair`, return blocking findings with the same brief and current diff, make the smallest repair, rerun fresh task validation, regenerate the package from the original task base, and re-review. After two failed repair rounds, raise capability one tier when available. Repeated evidence of a decomposition or requirement defect stops retries and routes to plan or specification repair.

## Completion semantics

A task becomes `Completed` only when implementation criteria, fresh validation, a valid executor-result handoff, and a passing `validate-executor-result` check all exist. `Completed` does not require `verdict: accept` unless review was required. Phase and plan completion derive from accepted children and declared dependency, barrier, and convergence gates.

Use typed blockers:

```text
context-blocked | repository-blocked | decision-blocked | validation-blocked
review-blocked | knowledge-blocked | workspace-blocked
```

Resume the owning step. Do not restart the lifecycle or create a repair specification for an ordinary task rejection.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`

Central `AGENTS.md` owns rule discovery and loading. Load the runtime rules above when their indexed conditions apply.

## Boundary

Follow `orch-orchestration-boundary` and `orch-handoff-required`.
