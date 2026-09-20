# WorkBundle Orchestration Workflow

WorkBundle separates semantic judgment from schema-owned mechanics. Agents interpret user purpose, accepted authority, product correctness, findings, qualification, and acceptance. Scripts validate schema, identity, bindings, canonical paths, scope safety, lifecycle transitions, stored bytes, and disposable index projections.

## Shared foundation

Resolve metadata-v4 workspace and repository authority before source work. Establish one Truth Basis containing purpose, as-is evidence, decision authority, expected delta, and conflict status. Use one bounded knowledge gateway before lightweight planning; execution consumes carried authority and does not retrieve durable knowledge.

Canonical artifacts are authority. Derived indexes are regenerable projections. Validate all necessary structural facts before authoritative mutation. After creation, perform only lightweight integrity/postcondition checks and truthfully report unavoidable partial effects.

## Specification

The agent authors complete specification semantics. The schema-backed writer owns structural fields, canonical location, immutable family identity, lifecycle movement, and index projection. A distinct reviewer advises on user-purpose alignment, authority, requirement/constraint/interface/acceptance coverage, conflicts, open questions, and scope. The controller/orchestrator assesses that advice and owns specification qualification.

## Planning

The agent authors root-plan, phase, and task semantics from a verified specification. Each artifact cites exact source IDs. The plan assigns ownership, dependencies, write scopes, task-local methodology, validation capability, and completion criteria. Static admission may report structural and graph facts but cannot qualify the plan. A distinct reviewer advises on the accuracy, completeness, decomposition, and executability of the complete current tree; the controller/orchestrator assesses that advice and owns qualification.

Repair current plan content at the existing canonical plan, phase, and task identities. Do not create active copies for intermediate review revisions. Return a verified plan to draft before child-content repair. After every repair, review the complete current tree against the verified specification and bounded source evidence; neither an earlier verdict nor a delta-only check qualifies the repaired content.

Do not optimize task or phase cardinality. Bound expected total orchestration cost at concrete independently owned production, dependency, validation, review, and repair seams. Every authoritative production path needs a production owner. Keep a coherent mechanical increment with one owner, oracle, and repair frontier together. Create phases only for an actual barrier or convergence boundary and reject speculative splits. When a task is materially under-decomposed, return to the plan and reslice only the affected region; do not repeatedly enlarge it.

Disposable task briefs and lightweight development plans compile accepted authority for execution. They are not durable semantic authority.

## Execution and executor results

Executors work only within bound task/repository/write scope. Behavior changes use task-local methodology and claim-relevant focused validation. Executors report facts; they never accept the product.

After execution, create one canonical `executor-result-v1` under the catalog-selected result location. It records implemented scope, changed paths, focused validation observations, unresolved product blockers, task fit, repository/CodeGraph facts, delegation, and knowledge disposition. Necessary structural and binding checks occur before mutation. Repair the active result at the same identity; do not retain intermediate revision copies. Historical handoffs, embedded statuses, override sidecars, and fallback indexes are unsupported and ignored.

## Direct implementation review

Freeze an exact commit or worktree candidate using a path-sorted changed-path manifest. A distinct reviewer compares the actual candidate directly with the verified specification and canonical plan, every planned feature and acceptance obligation, edge and failure behavior, and capable focused observations.

The reviewer issues an advisory `accept`, `repair`, or `blocked` assessment from product correctness. Passing tests cannot hide missing behavior. Missing or defective historical artifacts, indexes, knowledge state, or controller ceremony are separate supporting-state defects unless they make the product ambiguous, unsafe, inaccessible, or impossible to review. Store the advice in the current canonical `implementation-review-v2`; its `verdict` field is a recommendation, not orchestration authority. A complete re-review after repair updates that active identity instead of retaining intermediate verdict copies.

Reviewer execution may use read-only workspace isolation and transient provider diagnostics. Those operational facts do not become semantic or lifecycle authority and are not replayed by downstream consumers.

## Accepted continuation

After assessing the implementation review advice, the controller/orchestrator either routes repair/blocking or creates one canonical `accepted-task-result-v1`. It references the exact executor result, implementation review advice when required, current validation outcomes, product identity, unresolved material defects, and knowledge disposition. Repair its active identity in place. Dependencies and final review consume this compact controller decision without redispatching the executor or reconstructing review history.

## Final workflow review

A distinct final auditor performs one compact advisory pass over plan/task coverage, controller-accepted implementation decisions, relevant current tests, unresolved material defects, final knowledge disposition/return, repository finalization facts, and truthful archive readiness. The auditor does not reread source for code quality or repeat implementation review. The controller/orchestrator assesses that advice and owns the closure decision.

Store or repair the controller/orchestrator closure decision at one active canonical `final-workflow-review-v1` identity. Deterministic finalization carries that supplied decision and validates only canonical references, lifecycle state, clean baselines, archive destinations, index rebuilds, and binding release. Mechanical failure cannot manufacture or reinterpret a semantic decision.

## Knowledge disposition

Each meaningful validated move records `none`, `update`, `supersede`, or `reclassify`. Approved persistence is delegated to the appropriate `ks-*` owner. Orchestration never writes durable knowledge directly, and supporting knowledge state does not determine product qualification.

## Current command surface

- `build-task-brief`
- `write-executor-result`, `list-executor-results`, `transition-executor-result`, `index-executor-results`
- `build-implementation-review-candidate`
- `write-implementation-review`, `list-implementation-reviews`
- `write-accepted-task-result`, `list-accepted-task-results`
- `write-final-workflow-review`, `list-final-workflow-reviews`
- `finalize-reviewed-plan`

Legacy orchestration handoff, executor validation/adoption, review-history, and legacy finalization commands are unsupported.
