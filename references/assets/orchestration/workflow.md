# Orchestration Workflow

## Artifact chain

```text
specification -> plan -> phase -> task -> execute -> executor-result -> [optional task review]
                                                                    |
                                                                    v
                                               final workflow audit and finalization
```

Durable orchestration artifacts live under `.work-bundle/orchestration/`. Disposable task briefs, review packages, and lightweight development plans live under `.work-bundle/runtime/`; they have no active/archive/index lifecycle. Durable project knowledge remains owned by approved `ks-*` flows under `.work-bundle/knowledge/`.

Every development path uses the same five-field Truth Basis: purpose, as-is evidence, accepted decision authority, expected delta, and conflict status. Lightweight plans keep it compact and ephemeral. Heavy planning normalizes it in each task, then compiles it into the brief and review package. A material conflict stops through the existing typed route; no method invents authority.

## Semantic and coding methods

Semantic artifacts use `dev-semantic-convergence`: draft, view through caller-defined lenses, repair only discovered defects, and repeat until unchanged or blocked. Specifications use user purpose, authority support, requirement consistency, impact radius, knowledge disposition, and execution-workspace lenses. Plans use source-ID coverage, dependencies, write scopes, validation ownership, allocation, barrier safety, and executor-context completeness.

Coding tasks declare one primary method:

- `tdd` for testable new or changed behavior and diagnosed bug fixes;
- `systematic-debugging` before repairing unexpected behavior;
- `loop-coding` for behavior-preserving refactors with a green characterization baseline;
- `direct` for configuration, generated, documentation, and other non-testable mechanical work with exact deterministic checks.

## Specification and planning

Specifications preserve initial user-purpose evidence, bounded authority evidence, stable IDs, constraints, acceptance criteria, open questions, Knowledge Base Update disposition, and this policy when applicable:

```yaml
execution_workspace:
  isolation: required | preferred | existing
  profile: default | <named-profile>
  cleanup: after_integration | manual
```

Specification creation decides policy only; it does not provision a worktree. Planning carries that policy into executable tasks.

Plans keep durable artifacts normalized and DRY. Every executable task cites source IDs, the accepted Truth Basis, exact file scope, dependencies, validation, methodology, allocated rules/skills, a provider-neutral executor profile, and acceptance-review requirements. Decomposition does not optimize task or phase cardinality: it bounds expected total orchestration cost with concrete independently owned production, dependency, validation, review, and repair seams while preserving exact dependencies and disjoint write scopes. Every authoritative production path has a production owner; helper-only allocation cannot leave the path unowned. A coherent mechanical increment with one owner, oracle, and repair frontier stays together. A phase exists only for an actual barrier or convergence boundary, and speculative splits unsupported by current authority, repository, dependency, ownership, validation, or acceptance evidence are rejected. When simplification depends on a consequential assumption, the earliest ordinary task cheaply falsifies it before broad edits; do not add a checkpoint phase or risk-score lifecycle. Contract-decoupled parallel tasks share a stable contract group, validate only against that contract plus accepted handoffs and task-local files, reach a named barrier, and defer joint checks to the convergence owner.

When execution proves a task materially under-decomposed, return to the plan and reslice only the affected region at the newly evidenced seam. Preserve the original binding, baseline, and accepted unaffected regions; do not repeatedly enlarge the task or create a parallel retry lifecycle.

Generated specifications and plans record compact semantic convergence evidence:

```yaml
semantic_loop:
  result: converged | blocked
  rounds: 2
  repaired:
    - missing requirement coverage
```

## Compiled execution context

Before normal bounded execution, `build-task-brief` compiles the task, its cited source IDs, and the same five-field Truth Basis into a self-contained ephemeral packet. The packet resolves exact requirements, constraints, interfaces, file scope, methodology, allocated rules, validation commands, workspace root, handoff contract, and review requirement. Missing source IDs fail closed. Decision authority is semantically distinct from generic source IDs and must be `none-relevant` or an `AUTH-NNN` alias allocated from verified specification reconciliation; the compiler resolves each alias to `AUTH-NNN: <carried constraint>` without exposing knowledge paths. Invented, candidate, background, blocked, or superseded authority and any conflict block compilation.

For pre-commit acceptance, `build-review-package --head worktree` includes tracked, staged, unstaged, and untracked changes under a stable worktree identity while withholding protected-path content.

The normal executor reads the task brief, task-scoped source/tests, and explicitly allocated methodology skills. Full specification, root-plan, and phase reading is an escalation path when the brief is inconsistent or an acceptance reviewer detects a source-contract defect. Execution remains no-retrieval: executors do not query or read `.work-bundle/knowledge/`.

## Repository and workspace safety

Before compilation, delegation, or edits, resolve the containing workspace and every target repository from `.work-bundle/project.yaml`. Git-backed targets must match expected branch and accepted metadata baseline and report a clean worktree, unless a validated executor-result handoff explains exact expected changes. Never stash, reset, clean, restore, delete, or overwrite user work to pass preflight.

Use CodeGraph first only when a target contains `.codegraph/` and the work affects indexed source. Sync after preflight and before graph inspection, recheck cleanliness, and sync again after indexed changes. Record `no-index` and use bounded direct inspection when absent; do not initialize CodeGraph.

When isolation is required or preferred, `orch-execute-plan` selects or prepares an execution workspace and applies the named hydration profile. Temporary workspaces carry provenance and may be cleaned only when WorkBundle owns them, Git identity still matches, policy allows it, the worktree is clean, and durable provenance records confirmed integration or an explicit discarded/retired decision. Age makes a workspace stale for reporting but never proves a terminal lifecycle state. Never delete user or harness workspaces. Never copy credential values into task packets, prompts, handoffs, or worktrees; `credential-inject` uses the protected credential boundary.

## Task execution and acceptance

Full orchestration has three stage gates, separate from optional task review:
specification before `verified`, plan before execution, and integrated implementation
before plan `Completed` or archive. Native lifecycle commands read JSON/YAML
`stage-review-v1` envelopes under `.work-bundle/orchestration/reviews/`; a shape-valid
record or a self-declared `is_stale: false` is not sufficient. Direct writes with an
embedded terminal status also pass the gate. Binding creation/reuse and observed
task validation recheck current specification/plan reviews. Brief compilation alone
remains available for drafting. Lightweight development does not create these stages.

`review_runtime.artifact_review_identity(path)` binds artifact ID, version (default
`1`), and SHA-256 of canonical parsed front matter plus the complete body. Only
top-level `status`, `last_updated`, and `updated_at` are excluded so the approved
mechanical status transition does not invalidate itself. All other fields, including
review links, requirements and validation definitions, remain bound.
`plan_review_identity(workspace_root, plan_path)` aggregates the root and every
phase/task Markdown artifact declaring that plan ID, keyed by path under the plan
store, plus the identities of its linked specifications. A source, plan-member,
version, or body edit requires fresh review; old target
records remain history. These are semantic identities, not raw file checksums.
The final identity uses the same plan identity plus the resolved source repository's
current Git tree. Final admission requires a clean tracked/untracked source state;
a dirty checkout cannot claim that its HEAD tree is the reviewed candidate. Archive
rechecks admission after downstream acceptance checks, before moving artifacts.
Missing/ambiguous source repositories fail closed. Local tests do not substitute for
platform-specific release evidence. `validate_stage_reviews` requires all three
actual current target identities supplied by its lifecycle caller, not by reviews.

Reviewer capability is closed to `standard | judgment`. Evidence access uses
`direct_source | reproducible_snapshot | packet_only`; legacy `direct` maps to
direct-source access. Legacy `constrained_direct` and `carried_summary` context are
retained for blocked/repair evidence, never sole acceptance. Accepted review requires
direct-source or reproducible-snapshot context and no unavailable claim-relevant
evidence. Snapshot access additionally requires explicit snapshot artifact digests.
The record describes evidence access; lifecycle acceptance additionally requires
`reviewer_run: {run_id, sha256}` referencing a provider-specific reviewer-run receipt:
`reviewer-native-receipt-v1` for native host runs or
`reviewer-process-receipt-v1` for legacy sandboxed process runs.
Envelope validation alone (including historical records without that reference) is
not lifecycle admission. The gate resolves the controller-owned store through
`reviewer_runtime_root(workspace_root)` under `~/.work-bundle/reviewer-runtime/workspaces/`;
the envelope cannot select an arbitrary receipt path or store.

Before workspace creation, the controller adds `stage_review_context` to a stage direct
evidence packet: `stage`, `target_identity`, `target_locator` (a copied control
artifact), `agent_id`, `capability`, `execution_id`, and `evidence_mode`.
For task review it instead adds native `task_review_context`, binding the task target,
review mode/frontier or reset, reviewer identity/capability, execution identity, and
evidence mode. Workspace creation admits it only when the source checkout is clean and
its exact HEAD/tree still equal that task target.
The frozen packet builder derives `evidence_mode` from available evidence; requesting
`direct_source` does not grant it. The legacy process sandbox denies live source/control
access. The ordinary native host path consumes the same explicit frozen evidence,
suppresses author transport and user configuration, disables tools, and rejects observed
tool activity; native host read-only policy is not OS process isolation. A mechanically complete
`stage-evidence-manifest-v1` yields `reproducible_snapshot`; missing evidence yields
`packet_only`, which cannot grant acceptance, even with `unavailable_evidence: []`.
The manifest binds stage/target identity, required locators, roles, artifact digests,
and semantic authority identities. Its closure is derived from the current artifacts:

- Specification: the complete specification, carried `source_knowledge.constraint`
  authority, and file inputs declared by `truth_basis.as_is_evidence`. Protected
  knowledge origins are not retrieved; an absent carried constraint blocks completeness.
- Plan: the root, every phase/task declaring its plan ID, and every linked verified
  specification (including member-specific links and their required authority).
- Integrated implementation: the same authority closure, the complete clean Git source
  tree, and each validation-bearing member's current compact accepted result from its
  execution binding. Include its stored native task review when present; an older accepted
  representation remains valid without format migration. Historical executor handoffs are
  never scanned. The existing completion-provenance file is included when present.

For integrated snapshots, Git file modes/blob IDs reconstruct the exact target tree;
copied bytes are checked against those blobs before workspace creation. Symlinks,
submodules, unresolved/protected inputs, and unsupported authority references fail
closed. Ignored/generated dependencies are not a source-tree substitute: checks needing
them must declare the required inputs. The manifest and packet remain in the immutable
run receipt bundle after cleanup. Creation checks the manifest against live artifacts,
publication checks the frozen closure, and lifecycle admission re-derives current
stage membership and verifies the complete source-tree identity. Removing entries and
recomputing packet/receipt hashes cannot turn partial evidence into complete evidence.

`stage_target_identity` computes the target from current source artifacts, and
workspace creation checks it again. Complete stage evidence is checked before any
reviewer launch. Use `run_native_reviewer` for the ordinary plugin-independent native path;
`reviewer-process-run` remains the legacy sandboxed process runner. Specification and
plan workers retain the stage-review contract; task and
integrated-implementation product workers return the compact `task_review` judgment
defined by `dev-code-review`. The controller constructs the native envelope from frozen target, independence, and evidence context,
then binds its canonical digest into the receipt. The controller then attaches the run
ID and SHA-256 of the immutable receipt bytes to that exact result and publishes the
task-or-stage envelope as a read-only review-store record. Publication validates the provider-specific reviewer-run receipt once and persists an immutable direct
current-authority binding. Later lifecycle consumers use the immutable direct current-authority binding and recheck only its exact record and current target; they do
not traverse predecessors or replay receipt completeness. Bare stdout, unattached
receipts, and bare findings remain observations.

At publication, the lifecycle gate verifies review ID, exact result/target/profile,
successful completion, the provider-specific execution boundary, and immutable
packet/profile/event digests. Native receipts bind the executable, request, actual host run identity, sanitized
context, read-only policy, and absence of observed tool activity. Legacy process receipts
bind the sandbox, denied network, and scratch-only write boundary. Run-scoped evidence
remains available after workspace cleanup; full traces
are never embedded into the stage envelope. Missing, altered, failed, mutable, or
mismatched provenance cannot grant acceptance. Known execution IDs are obtained
from artifact `execution_id`, `author_execution_id(s)`, `repair_execution_id(s)` and
current plan execution bindings; overlap with the reviewer execution/run ID blocks
admission. Undeclared author identities cannot be inferred.

The controller/runtime store is a trusted boundary, not a cryptographic defense
against a compromised same-OS-user host. The receipt proves the launched worker's
process/evidence boundary and binds its controller-selected capability; it does not
turn a mechanical fixture into semantic review. WOR-108 mandatory task ownership
and bounded context/history projection remain separate.

Deterministic observation reuse retains the existing complete evidence identity and
freshness policy. The provenance store reserves each identity with an OS-released
file lock, executes outside the shared store lock, then rereads and publishes under
the shared lock. Different identities can run concurrently; identical identities
remain single-flight. Publication rejects an intervening mutation epoch or expired
freshness. Reservation lock files are retained to avoid splitting concurrent waiters;
they are runtime artifacts, not source inputs or a separate cache subsystem.

Task code review consumes one product candidate compiled from accepted product
requirements/boundaries, exact product source/diff identity, normalized harness
observations, and unresolved product concerns. Handoff, knowledge, reviewer-history,
receipt/publication, status, and archive bookkeeping remain controller inputs and do
not enter product judgment. Controller/orchestration code is product when allocated
by the accepted task.

Reviewer observations remain intact. The controller owns their classification, the
first broken owner or artifact, and the selected action through the agent-owned v2
contract; current routing has no fixed class-to-remedy table or confirming-review step.

Plan identity uses the documented `plan-structural-projection-v2`: lifecycle fields are
excluded only at designated structural locations, while unknown or substantive nested
fields and requirement text remain identity-bearing. The original projection remains
callable only for explicit legacy interpretation; current writes always use v2.

The **acceptance once** lifecycle rule makes the harness strongly verify binding,
source/scope, subagent ownership, validation, and required review, then persists one
compact accepted result. Dependency release, finalization, resume, and archive consume
that result plus a current harness observation while its identity and freshness hold;
they do not replay transient acceptance evidence or historical handoff chains. A
status-only or append-only evidence change neither invalidates the canonical semantic
plan projection nor causes a terminal rerun.
A later stored task repair review recomposes this compact result through the existing
materializer while preserving executor-result, validation, owner, baseline, and
knowledge authority; it performs no executor redispatch, handoff rewrite, validation
rerun, or review-history embedding.

Capability context projects trusted intent/evaluation seeds through the existing
typed-relation traversal (`light`: 1 hop, `standard`: 2, `deep`: 4), bounded by
`max_nodes`. Stale/non-authoritative nodes cannot be transit nodes; frontier and
stopping reason expose depth/node-budget limits. Required evaluation seeds retain
their ordering priority. This does not introduce an initial-versus-repair frontier.

```text
scheduler selects executable task
  -> compile task brief
  -> choose provider-neutral capability
  -> bind mandatory subagent owner or fail closed before mutation
  -> dispatch every planner-approved disjoint ready task before waiting
  -> subagent implements with declared methodology
  -> run fresh task-local validation
  -> creation-safe validation and atomic executor-result handoff write
  -> optional task review when compiled review_required: true
     -> compile bounded review package
     -> independent `dev-code-review`
     -> accept | repair | blocked
  -> accepted-result materialization joins executor facts, observations, and stored review authority
  -> Completed
```

Subagent executors own every implementation and repair mutation, task-local verification, and executor-result evidence, including a task-local knowledge disposition of `none`, `update`, `supersede`, or `reclassify`. They never invoke persistence or read knowledge. Product reviewers judge accepted product requirements/boundaries, exact source/diff, correctness, edge cases, normalized validation observations, unresolved product concerns, and unnecessary complexity. Controllers own disposition, handoff, provenance, publication, and lifecycle mechanics. Schedulers own dependencies, barriers, context compilation, neutral subagent binding, validation routing, and evidence shape; they do not perform code-quality review or mutate task write scope.

Selecting `orch-execute-plan` requires a subagent owner for every task without a separate user opt-in. The production `TaskOwnershipScheduler` admission entry consumes a host-native adapter or, when available, an Execution-Flow adapter; host-native execution is sufficient and Execution Flow is optional. Evidence records only the minimum agent/run identity and mechanism. If none is available, execution fails closed before task mutation. Independent disjoint tasks in distinct execution workspaces dispatch before any wait; dependent, overlapping, or same-workspace tasks serialize. Acceptance uses the same scheduler entry to reject controller mutation, and repair dispatch uses `operation: repair` through the same adapter path.

On `repair`, return blocking findings to the existing task owner, repair from the exact
previously reviewed source, rerun only claim-relevant invalidated validation, and
perform one scoped rereview. Preserve unaffected accepted executor/validation authority.
Initial acceptance uses one executor-result handoff; accepted-task source repair consumes
the compact accepted result; publication-only/control resume reuses the completed
judgment and never redispatches, rewrites a handoff, or reruns validation/review.

On reviewer infrastructure or provider failure, repair the first broken runner/provider
against the same immutable review package; a capable independent reviewer may be reused,
and completed judgment publication is idempotent. Source identity, validation evidence,
plan decomposition, and review frontier remain unchanged. A finding-scoped repair under unchanged authority
carries the previous finding/evidence frontier and reviews only repaired boundaries.
Only a material authority, scope, acceptance, decomposition, or validation-allocation
change resets review to an initial frontier.

A task becomes `Completed` only when implementation criteria, fresh validation, a valid immutable executor-result handoff, and a passing `validate-executor-result` check all exist. Review-required tasks additionally require exact stored `accept` authority, joined only during accepted-result materialization. Phase and plan status derive from accepted children plus declared dependency and barrier gates.

`write-handoff` resolves the compiled task and runs its pure creation-safe projection before artifact or handoff-index mutation. This admits structurally complete executor facts before independent observation or review while rejecting wrong-owner review, receipt, publication, accepted-result, and audit fields. New handoffs use `lifecycle_authority: location-v1`: status directories own current lifecycle state, status changes move identical bytes, and same-state requests write nothing. Unmarked legacy artifacts retain embedded/location fallback until their first explicit status change creates the bounded digest/type/plan/task/status override; no historical bytes are rewritten.

## Bounded post-execution review and closure

The optional workspace policy in `.work-bundle/project.yaml#orchestration_control` fixes the post-execution review round limit at five and projects stable per-flow state. The append-only controller ledger under `.work-bundle/runtime/orchestration-control/` owns round history. Plan and specification revisions do not consume post-execution review rounds; neither do task reviews, reviewer/provider retries, publication retries, resumes, or branches. Legacy workspaces without this policy keep their existing behavior.

Once all executor attempts are terminal, the controller runs `begin-review-round` before integrated-review evidence preparation or dispatch. An exact request ID and target identity is idempotent; a different target identity reserves a new round. After publication, `complete-review-round` consumes the immutable store-owned product review reference. If no product artifact exists because the controller was blocked, a factual audit-block may complete the attempt as blocked, but it must not impersonate a product verdict. Duplicate exact completion does not increment. `review-round-status` reports the frozen target, reserved/completed counts, and finalization state.

An accepted round continues through the normal final workflow audit, knowledge gate, archive, and index refresh. Findings below the fifth completed round route through admission-controlled scoped repair. The fifth unresolved or blocked completion stops reconciliation and invokes `finalize-with-blockers`: persist finalization-required state, validate the supplied residual specification and clean source baselines, persist an active workspace blocker, finalize the review-owned knowledge disposition, archive the origin specification and plan and update their indexes without collision overwrite, release owned bindings, and persist terminal closure. Incomplete administrative stages remain explicit and retryable, but retry must not reopen product work.

Shared admission uses operation classes instead of caller-selected labels. An exhausted flow refuses reconciliation before its blocker is written. An active workspace blocker refuses ordinary new work and other unexempted reconciliation; read-only diagnosis, round completion, blocker recording, knowledge return, and finalization remain available. Any bounded implementation exemption names the exact flow and blocker and restores its exact backed-up blocker without losing newer unrelated metadata.

The builtin `orch-bounded-closure` rule and its index entry are the deployment target. If an already-installed workspace has a project-scope shim with that same rule ID, retain the project shim until builtin deployment is ready, then remove only that owned shim in the same bounded migration. Never enable both copies or mutate unrelated project rules.

Current metadata migration renames only the legacy policy key to `post_execution_review_round_limit: 5`; it never scans or rewrites historical specifications, plans, handoffs, reviews, or evidence.

## Failure routing

Use only these blocker classes:

```text
context-blocked       missing or inconsistent compiled context
repository-blocked    branch, baseline, metadata, or repository finalization failure
decision-blocked      unresolved requirement, API, architecture, or authority decision
validation-blocked    required validation absent or failing
review-blocked        missing or rejected acceptance evidence
knowledge-blocked     required ks-* work or return evidence incomplete
workspace-blocked     execution workspace preparation, hydration, ownership, or cleanup failure
```

Resume the step that owns the failure. Repair a task for rejected implementation, a plan for decomposition defects, and a specification only for requirement, design, or authority defects.

Before responding to any evaluator, review, validation, or lifecycle failure, classify
the exact failing assertion into a causal class and route it to the first owning layer.
An evaluator expectation cannot create source authority. Historical validation uses an
exact baseline and endpoint rather than an open-ended live HEAD, and issue-run artifacts
remain in the workspace control plane; proven historical cleanup does not turn old
accepted manifests into a live source inventory.

## Final workflow audit

`orch-review-plan` audits workflow completion, required optional reviews, declared plan-level/integration acceptance, handoff integrity, knowledge disposition, finalization gates, and archive readiness. It checks declared completion evidence against the compiled Truth Basis, source IDs, expected delta, and remaining AUTH constraints. It does not redo task code review, reread implementation for code quality, or start another implementation-review agent.

Final review aggregates accepted task dispositions from execution and task-review evidence. Any accepted `update`, `supersede`, or `reclassify` promotes durable closure to `required` even when the specification's upstream Knowledge Base Update state was `not-needed`; accepted `none` does not. Rejected task dispositions do not trigger closure. Archive is allowed only after required optional reviews are accepted, declared plan-level/integration acceptance is recorded, validation and handoffs are coherent, barriers converged, the resulting Knowledge Base Update disposition is `completed` or `not-needed`, approved `ks-*` return evidence exists when required, and allowed commit/CodeGraph/metadata/archive/index mechanics complete or are explicitly inapplicable. Missing stored review authority is not a blocker when no compiled task set `review_required: true`.

Knowledge closure gates final completion and archive; it never precedes specification, plan, task, or integrated-implementation review.

Only approved keep-summarizing owners write durable knowledge. Final orchestration review owns approved persistence delegation and may invoke that owner, then validate returned paths or an evidence-backed no-write result; executors and orchestration itself must not write knowledge directly.

Specification authoring materializes `impact_decisions` from bounded current-state evidence about the requested surface, upstream/downstream relations, validation surfaces, and relevant dirty work. A relation is material only when its disposition could change a requirement, constraint, acceptance criterion, user-observable or contractual outcome, architectural boundary, measurable quality target, validation target, or declared boundary. Each material relation is `accepted | excluded | blocking`: accepted relations use `projects_to` for stable specification IDs, excluded relations require evidence, and blocking relations prevent verification. Stop when further exploration could change none of those surfaces and record the reason; a greenfield result may use `none_relevant` only with the searched boundary, reason, and `stopping_reason`. Targeted Git history, prior work artifacts, execution evidence, or durable knowledge is an escalation for contradiction, unresolved ownership, material regression/causality, or suspected governing legacy decisions—not mandatory full-history archaeology or broad knowledge retrieval. This impact-decision view is compared by semantic convergence; repository traversal remains owned by specification authoring.

Within existing Design Interrogation, specification authoring also records one `excellence_applicability` result after one compact pass: `no_material_opportunity` with an evidence-backed reason, or `material_opportunities` with proposals selected from task evidence and change shape rather than a universal checklist. Surface an option only when accepting or rejecting it could change a requirement, constraint, acceptance criterion, user-observable or contractual outcome, architectural boundary, measurable quality target, validation target, or declared boundary. Each proposal records user value, evidence, cost, risk, recommendation, and `accepted | rejected | deferred | not_material`; unanswered proposals become deferred. Only accepted proposals may project through stable IDs into authoritative requirements, constraints, interfaces, acceptance criteria, or validation targets. Other proposals remain traceable but excluded from planning, executor briefs, and acceptance obligations. The pass stops when further exploration could change none of those surfaces, records the reason, and ensures every surfaced proposal has a disposition. It does not add a lifecycle stage, force a recommendation, or make optional proposals blocking unless accepted projection is incomplete or an unresolved safety or authority conflict exists. The excellence-applicability view is compared by semantic convergence, while agent judgment owns opportunity materiality and recommendation quality.

Planning allocates every accepted validation-bearing obligation or design decision to stable `evidence_capability` entries before execution. Each entry names `source_ids`, invariant, boundary, oracle, `capability_reason`, `freshness`, `task_id`, task-local `evidence_ids`, and initializes `closure_result: pending`; task briefs and review packages compile only the owning task's entries. A completed mapped task returns `evidence_closure` under the same INV/VAL identities. The harness observes those compiled validation items directly and closure fails on missing, incapable, contradictory, stale, wrong-boundary, failed, or unexecuted evidence, routing repair to the first owning task, plan, or specification. Executor-authored closure is corroboration, not independent proof. Use `no_validation_bearing_obligation + reason` only when no accepted validation-bearing obligation exists, never from a WOR-61 `none_relevant` impact result alone. Select the lightest capable boundary per invariant rather than imposing universal runtime, browser, visual, performance, or E2E proof. Mechanical helpers validate IDs, completeness, task ownership, provenance, and observed results; agents own semantic capability judgment.

## Lightweight development lane

Use `dev-create-task-plan` for bounded mechanical work with stable decisions. After preflight and source grounding it invokes one bounded `ks-what-is-helpful` gateway, carries accepted authority or evidence-backed `none relevant`, writes one disposable plan under `.work-bundle/runtime/dev-plans/`, and creates no orchestration artifact tree. Its lightweight completion owner records an evidence-backed no-write result for `none`; for `update`, `supersede`, or `reclassify`, it invokes the approved keep-summarizing lifecycle and validates return evidence before completion. Escalate to full orchestration for unresolved architecture/API/data/workflow decisions, wide impact, multiple repositories, migration/deployment sequencing, unresolved durable-knowledge decisions, or parallel contract/barrier needs.
