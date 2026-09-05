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

Plans keep durable artifacts normalized and DRY. Every executable task cites source IDs, the accepted Truth Basis, exact file scope, dependencies, validation, methodology, allocated rules/skills, a provider-neutral executor profile, and acceptance-review requirements. Decomposition uses minimum orchestration overhead while preserving Truth Basis continuity, independently falsifiable and testable increments, short evidence loops, dependencies, disjoint write scopes, validation ownership, bounded failure radius, and review boundaries; one sound mechanical increment is not split merely to minimize size. When simplification depends on a consequential assumption, the earliest ordinary task cheaply falsifies it before broad edits; do not add a checkpoint phase or risk-score lifecycle. Contract-decoupled parallel tasks share a stable contract group, validate only against that contract plus accepted handoffs and task-local files, reach a named barrier, and defer joint checks to the convergence owner.

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
`reviewer_run: {run_id, sha256}` referencing a native `reviewer-process-receipt-v1`.
Envelope validation alone (including historical records without that reference) is
not lifecycle admission. The gate resolves the controller-owned store through
`reviewer_runtime_root(workspace_root)` under `~/.work-bundle/reviewer-runtime/workspaces/`;
the envelope cannot select an arbitrary receipt path or store.

Before workspace creation, the controller adds `stage_review_context` to the direct
evidence packet: `stage`, `target_identity`, `target_locator` (a copied control
artifact), `agent_id`, `capability`, `execution_id`, and `evidence_mode`.
The current sandbox denies live source/control access, so its packet builder derives
`evidence_mode`; requesting `direct_source` does not grant it. A mechanically complete
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
  tree, and executor handoffs containing evidence for each declared validation command
  or inspection ID. The existing native completion-provenance file is included when
  present. This is evidence availability, not a replacement validation-result verdict;
  existing freshness, binding, authorization, and platform acceptance gates still apply.

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
workspace creation checks it again. Run the worker with `reviewer-process-run` using
that runtime root. Its stdout must be exactly one stage-review JSON object, without
`reviewer_run`; the native publisher verifies it against the frozen context and
binds its canonical digest into the receipt. The controller then attaches the run
ID and SHA-256 of the immutable receipt bytes to that exact result.

The lifecycle gate verifies review ID, exact result/target/profile, successful
completion, sandbox/network/write boundary, and immutable packet/profile/event
digests. Run-scoped evidence remains available after workspace cleanup; full traces
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

Capability context projects trusted intent/evaluation seeds through the existing
typed-relation traversal (`light`: 1 hop, `standard`: 2, `deep`: 4), bounded by
`max_nodes`. Stale/non-authoritative nodes cannot be transit nodes; frontier and
stopping reason expose depth/node-budget limits. Required evaluation seeds retain
their ordering priority. This does not introduce an initial-versus-repair frontier.

```text
scheduler selects executable task
  -> compile task brief
  -> choose provider-neutral capability
  -> implement with declared methodology
  -> run fresh task-local validation
  -> write executor-result handoff
  -> validate-executor-result
  -> optional task review when acceptance_review.required: true
     -> compile bounded review package
     -> independent `dev-code-review`
     -> accept | repair | blocked
  -> Completed
```

Executors own implementation, task-local verification, and executor-result evidence, including a task-local knowledge disposition of `none`, `update`, `supersede`, or `reclassify`. They never invoke persistence or read knowledge. Reviewers own acceptance judgment for the accepted Truth Basis, requirement fit, correctness, edge cases, test oracle, disposition, unnecessary complexity, allocated obligations, and validation sufficiency. Schedulers own dependencies, barriers, context compilation, delegation, and evidence shape; they do not perform code-quality review.

Visible multi-agent subagents are preferred only when user/environment policy allows and write scopes are disjoint. Invisible helper workers may support bounded analysis but never own delegated task implementation. When independent subagents are unavailable, record `reviewer_independent: false` and perform an explicit reduced-independence second pass.

On `repair`, return blocking findings with the same brief and current diff, make the smallest repair, rerun claim-relevant validation, regenerate the package from the original base, and review again. After two failed low-cost repair rounds, escalate the capability tier; if evidence indicates a plan or specification defect, stop the retry loop and route the typed blocker.

A task becomes `Completed` only when implementation criteria, fresh validation, a valid executor-result handoff, and a passing `validate-executor-result` check all exist. `Completed` does not require `verdict: accept` unless review was required. Phase and plan status derive from accepted children plus declared dependency and barrier gates.

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

## Final workflow audit

`orch-review-plan` audits workflow completion, required optional reviews, declared plan-level/integration acceptance, handoff integrity, knowledge disposition, finalization gates, and archive readiness. It checks declared completion evidence against the compiled Truth Basis, source IDs, expected delta, and remaining AUTH constraints. It does not redo task code review, reread implementation for code quality, or start another implementation-review agent.

Final review aggregates accepted task dispositions from execution and task-review evidence. Any accepted `update`, `supersede`, or `reclassify` promotes durable closure to `required` even when the specification's upstream Knowledge Base Update state was `not-needed`; accepted `none` does not. Rejected task dispositions do not trigger closure. Archive is allowed only after required optional reviews are accepted, declared plan-level/integration acceptance is recorded, validation and handoffs are coherent, barriers converged, the resulting Knowledge Base Update disposition is `completed` or `not-needed`, approved `ks-*` return evidence exists when required, and allowed commit/CodeGraph/metadata/archive/index mechanics complete or are explicitly inapplicable. Missing review verdicts are not a blocker when no task set `acceptance_review.required: true`.

Only approved keep-summarizing owners write durable knowledge. Final orchestration review owns approved persistence delegation and may invoke that owner, then validate returned paths or an evidence-backed no-write result; executors and orchestration itself must not write knowledge directly.

Specification authoring materializes `impact_decisions` from bounded current-state evidence about the requested surface, upstream/downstream relations, validation surfaces, and relevant dirty work. A relation is material only when its disposition could change a requirement, constraint, acceptance criterion, user-observable or contractual outcome, architectural boundary, measurable quality target, validation target, or declared boundary. Each material relation is `accepted | excluded | blocking`: accepted relations use `projects_to` for stable specification IDs, excluded relations require evidence, and blocking relations prevent verification. Stop when further exploration could change none of those surfaces and record the reason; a greenfield result may use `none_relevant` only with the searched boundary, reason, and `stopping_reason`. Targeted Git history, prior work artifacts, execution evidence, or durable knowledge is an escalation for contradiction, unresolved ownership, material regression/causality, or suspected governing legacy decisions—not mandatory full-history archaeology or broad knowledge retrieval. This impact-decision view is compared by semantic convergence; repository traversal remains owned by specification authoring.

Within existing Design Interrogation, specification authoring also records one `excellence_applicability` result after one compact pass: `no_material_opportunity` with an evidence-backed reason, or `material_opportunities` with proposals selected from task evidence and change shape rather than a universal checklist. Surface an option only when accepting or rejecting it could change a requirement, constraint, acceptance criterion, user-observable or contractual outcome, architectural boundary, measurable quality target, validation target, or declared boundary. Each proposal records user value, evidence, cost, risk, recommendation, and `accepted | rejected | deferred | not_material`; unanswered proposals become deferred. Only accepted proposals may project through stable IDs into authoritative requirements, constraints, interfaces, acceptance criteria, or validation targets. Other proposals remain traceable but excluded from planning, executor briefs, and acceptance obligations. The pass stops when further exploration could change none of those surfaces, records the reason, and ensures every surfaced proposal has a disposition. It does not add a lifecycle stage, force a recommendation, or make optional proposals blocking unless accepted projection is incomplete or an unresolved safety or authority conflict exists. The excellence-applicability view is compared by semantic convergence, while agent judgment owns opportunity materiality and recommendation quality.

Planning allocates every accepted validation-bearing obligation or design decision to stable `evidence_capability` entries before execution. Each entry names `source_ids`, invariant, boundary, oracle, `capability_reason`, `freshness`, `task_id`, task-local `evidence_ids`, and initializes `closure_result: pending`; task briefs and review packages compile only the owning task's entries. A completed mapped task returns `evidence_closure` under the same INV/VAL identities. The harness observes those compiled validation items directly and closure fails on missing, incapable, contradictory, stale, wrong-boundary, failed, or unexecuted evidence, routing repair to the first owning task, plan, or specification. Executor-authored closure is corroboration, not independent proof. Use `no_validation_bearing_obligation + reason` only when no accepted validation-bearing obligation exists, never from a WOR-61 `none_relevant` impact result alone. Select the lightest capable boundary per invariant rather than imposing universal runtime, browser, visual, performance, or E2E proof. Mechanical helpers validate IDs, completeness, task ownership, provenance, and observed results; agents own semantic capability judgment.

## Lightweight development lane

Use `dev-create-task-plan` for bounded mechanical work with stable decisions. After preflight and source grounding it invokes one bounded `ks-what-is-helpful` gateway, carries accepted authority or evidence-backed `none relevant`, writes one disposable plan under `.work-bundle/runtime/dev-plans/`, and creates no orchestration artifact tree. Its lightweight completion owner records an evidence-backed no-write result for `none`; for `update`, `supersede`, or `reclassify`, it invokes the approved keep-summarizing lifecycle and validates return evidence before completion. Escalate to full orchestration for unresolved architecture/API/data/workflow decisions, wide impact, multiple repositories, migration/deployment sequencing, unresolved durable-knowledge decisions, or parallel contract/barrier needs.
