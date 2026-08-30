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

Specification authoring materializes `impact_decisions` from bounded current-state evidence about the requested surface, upstream/downstream relations, validation surfaces, and relevant dirty work. Each material relation is `accepted | excluded | blocking`: accepted relations use `projects_to` for stable specification IDs, excluded relations require evidence, and blocking relations prevent verification. A greenfield result may use `none_relevant` only with the searched boundary, reason, and `stopping_reason`. Targeted Git history, prior work artifacts, or execution evidence is an escalation for contradiction, unresolved ownership, material regression/causality, or suspected governing legacy decisions—not mandatory full-history archaeology. This impact-decision view is compared by semantic convergence; repository traversal remains owned by specification authoring.

## Lightweight development lane

Use `dev-create-task-plan` for bounded mechanical work with stable decisions. After preflight and source grounding it invokes one bounded `ks-what-is-helpful` gateway, carries accepted authority or evidence-backed `none relevant`, writes one disposable plan under `.work-bundle/runtime/dev-plans/`, and creates no orchestration artifact tree. Its lightweight completion owner records an evidence-backed no-write result for `none`; for `update`, `supersede`, or `reclassify`, it invokes the approved keep-summarizing lifecycle and validates return evidence before completion. Escalate to full orchestration for unresolved architecture/API/data/workflow decisions, wide impact, multiple repositories, migration/deployment sequencing, unresolved durable-knowledge decisions, or parallel contract/barrier needs.
