---
name: orch-execute-plan
description: 'Execute a WorkBundle task, phase, or plan through mandatory subagent task ownership, compiled task briefs, task-local methodology, optional independent acceptance review, and dependency-aware scheduling.'
---

# orch-execute-plan

## Execution Constraints (skill-owned)

Execution is a no-retrieval stage. Use the selected task, its compiled Truth Basis and cited specification values, declared prior handoffs, task-scoped source/tests, and allocated methodology. Do not query or read `.work-bundle/knowledge/`.

## Scheduler-Owned Constraints

1. Resolve target task, phase, or plan and its executable dependency queue.
2. Before compilation, capability selection, delegation, or edits, resolve the workspace and every target repository from `.work-bundle/project.yaml`. Git-backed targets must match branch and accepted metadata baseline and be clean unless validated handoffs explain exact changes. Never mutate user work to pass preflight.
3. Record CodeGraph applicability per target. When `.codegraph/` exists for indexed source work, sync after preflight and query it before broad inspection; recheck cleanliness and sync after changes. Otherwise record `no-index` and use bounded direct inspection. Do not initialize CodeGraph.
4. Select or prepare the declared execution workspace and hydration profile. Record provenance. Cleanup may remove only a clean WorkBundle-owned workspace whose expected Git identity still matches, whose policy allows cleanup, and whose durable lifecycle state confirms integration or an explicit discarded/retired decision. Age alone is report-only; never delete user or harness workspaces.
5. After scheduler workspace selection or preparation and before material edits, create or load one harness-owned task execution binding that carries plan/task identity, `workspace_id`/`execution_id`/`repository_id`, and exact path/Git provenance. Keep it in runtime/execution-workspace state outside the mutation envelope. Compile and read task/spec artifacts from the control WorkBundle root. Execute process and Git evidence against the bound execution repository. Do not point orchestration `--project-root` at an isolated worktree to load gitignored `.work-bundle/orchestration/**`. Capture the pre-task baseline once from that bound repository via the helper; later brief rebuild or repair must not recapture or replace it. Executor handoff and other supported executor-facing interfaces cannot supply or replace that baseline. Same-user filesystem rewrite of helper runtime files is out of scope. Mutating siblings on the same execution path isolate via prepare_worktree or serialize even when write scopes are disjoint; a shared worktree must not host them. Do not add a path-ownership ledger.
6. Compile the bounded task brief:

```bash
python3 scripts/orch.py build-task-brief --task <task-path>
```

Missing source IDs; decision authority other than `none-relevant` or an `AUTH-NNN` alias whose carried constraint was reconciled in the verified specification; `conflict_status: escalate`; inconsistent scope; or unsafe workspace state fails closed with the existing typed blocker. Truth Basis conflict uses `decision-blocked`. The compiled brief includes `AUTH-NNN: <carried constraint>`, not the alias alone.
7. Choose the provider-neutral capability from the task profile. Consume planner-proven dependencies, write scopes, common-contract groups, barriers, convergence ownership, and isolation requirements. Dispatch every ready independent task with disjoint write scope to a separate execution workspace before awaiting any result. Serialize dependent, overlapping, or same-workspace mutation. Contract-decoupled participants validate against the common contract, accepted prior handoffs, and task-local files; they reach the named barrier before convergence work.
8. Selecting `orch-execute-plan` makes every implementation and repair task subagent-owned. Use the production `TaskOwnershipScheduler` entry in `scripts/orchestration/task_ownership.py` with a host-native or Execution-Flow adapter; do not reproduce its admission logic in prompts or detached helpers. Before any task mutation, it confirms adapter availability and binds each dispatched task to validated neutral agent/run provenance. If no subagent is available, it fails closed with `workspace-blocked`; there is no controller or single-agent fallback. Do not substitute `reviewer_independent: false` for a missing task owner. The orchestration thread may schedule, compile briefs, coordinate barriers, validate results, route reviews, and manage lifecycle, but it must not implement or repair task write scope.
9. Use `TaskOwnershipScheduler.validate_acceptance` to validate neutral `delegation_evidence` and reject acceptance when mutation provenance shows the controller changed task-owned write scope, even if validation is green. Run the pure creation-safe projection before the helper atomically writes/indexes the immutable executor result; it rejects malformed executor facts and wrong-owner review/control fields without observing, reviewing, or accepting. For a mapped capability task, report each validation under its compiled evidence ID and invariant IDs, and add `evidence_closure` using the allocated boundary, freshness, and evidence IDs. The later terminal helper observes required process/inspection items in the bound worktree as one Git-state-neutral batch, reuses the compiled identities, and rejects missing, incapable, contradictory, stale, wrong-boundary, failed, or unexecuted evidence before authorizing from post-execution task-caused delta. Executor closure claims are corroboration, not harness proof. Compile `build-review-package` and assign `dev-code-review` only when compiled `review_required: true`. The scheduler does not perform code-quality review.

```bash
python3 scripts/orch.py validate-executor-result --task <task-path> --handoff <handoff-path>
```

## Executor-Owned Constraints

- Follow the compiled brief and its exact read/write/forbidden scope.
- Own implementation and repair task mutation as the bound subagent; return neutral `agent_id`, `run_id`, and `mechanism` provenance without UI or visibility fields.
- Load or acknowledge allocated rules and methodology before the operation they govern.
- Create or load the harness-owned task execution binding before material edits; capture the pre-task baseline once; run process commands and named inspections only in the bound execution repository.
- Apply `systematic-debugging` before proposing a root-cause fix for unexpected behavior.
- Apply TDD to testable new/changed behavior and diagnosed fixes; use direct deterministic verification for non-testable mechanical artifacts.
- Run fresh claim-relevant validation after the final edit.
- Write a sparse `executor-result-v1` handoff containing only executor-owned task identity, changed paths, validation, repository/CodeGraph fallback, allocated obligations, unresolved blockers, local task-fit evidence, and a knowledge disposition of `none`, `update`, `supersede`, or `reclassify`. Omit review, receipt, publication, accepted-result, and later audit facts.
- Knowledge disposition contains task-local evidence only. It must not name knowledge paths, invoke any `ks-*` skill, or authorize persistence; final orchestration review owns approved follow-up.
- Do not perform acceptance judgment or mark a review-required task complete.
- Trigger `wb-defect-evaluation` only for a new unintended WorkBundle-related conflict, error, failed validation, or contradictory workflow behavior. Stop once visible relatedness is established; no chain-of-thought or exhaustive tracing is required.

## Independent task review

When compiled `review_required: true`, validate initial executor facts without demanding or embedding the future review verdict, then build the product candidate only from accepted product requirements/boundaries, exact base/current product source and diff identity, harness-owned normalized validation observations, and unresolved product concerns. Handoff, knowledge, reviewer-history, receipt/publication, status, and archive bookkeeping are not product-review inputs or findings. Controller/orchestration code is still product when the task allocates it. Skip this hop when review is not required.

```bash
python3 scripts/orch.py build-review-package \
  --task <task-path> --handoff <handoff-path> --base <git-ref> --head <git-ref>
```

Use `--head worktree` for pre-commit review; the compiler includes tracked, staged, unstaged, and untracked changes, assigns a stable worktree identity, and withholds protected-path content.

The reviewer uses only that bounded product candidate and `dev-code-review`, returning compact `accept|repair` product judgment. Invalid or incomplete input is a controller input/runner failure outside the product verdict. The controller composes the native envelope, verifies independent provenance, and publishes it. A task or stage verdict becomes lifecycle authority only after the exact result and its provider-specific reviewer-run receipt are stored and validated against controller-authorized target identity.

If reviewer infrastructure or provider failure prevents a verdict, preserve the immutable package and repair the first broken runner/provider owner. A capable independent reviewer may be reused. Do not change source, rerun validation, reslice, or require identity rotation for provider availability. Publication retry after a completed judgment reuses the exact result and receipt.

On `repair`, return blocking findings to the existing task owner. Repair from the exact previously reviewed source, rerun only claim-relevant validation invalidated by the repair, and perform one scoped rereview of the affected frontier. Reuse unaffected executor and validation authority. Only a material authority, scope, acceptance, decomposition, or validation-allocation change resets to an initial frontier. Publication-only/control resume never redispatches the executor or reruns validation/review.

## Completion semantics

A task becomes `Completed` only when implementation criteria, fresh validation, neutral subagent ownership provenance, no controller mutation of task write scope, a valid immutable executor-result handoff, and a passing `validate-executor-result` check all exist. A review-required task additionally needs exact stored `accept` authority; accepted-result materialization alone joins it with executor facts and current observations. Phase and plan completion derive from accepted children and declared dependency, barrier, and convergence gates.

Enforce acceptance once: after the helper verifies binding, source/scope, subagent ownership, validation, and stored required-review authority, persist one compact accepted result. A later stored task repair review recomposes that result through the existing materializer, preserving executor and validation authority without redispatch, handoff rewrite, validation rerun, or embedded review history. Dependency release and later lifecycle steps consume the compact result plus current harness observations; they do not replay transient acceptance evidence or historical handoff chains.

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
