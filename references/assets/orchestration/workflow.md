# WorkBundle Orchestration Workflow

WorkBundle separates semantic judgment from schema-owned mechanics. Agents interpret user purpose, accepted authority, product correctness, findings, qualification, and acceptance. Scripts validate schema, identity, bindings, canonical paths, scope safety, lifecycle transitions, stored bytes, and disposable index projections.

## Shared foundation

Resolve metadata-v4 workspace and repository authority before source work. Establish one Truth Basis containing purpose, as-is evidence, decision authority, expected delta, and conflict status. Use one bounded knowledge gateway before lightweight planning; execution consumes carried authority and does not retrieve durable knowledge.

Canonical artifacts are authority. Derived indexes are regenerable projections. Validate all necessary structural facts before authoritative mutation. After creation, perform only lightweight integrity/postcondition checks and truthfully report unavoidable partial effects.

For registered specification, root-plan, phase, task, executor-result, implementation-review, accepted-result, and final-review families, use semantic payload → `scripts/orch.py write-spec`, `write-plan`, `write-phase`, `write-task`, `write-executor-result`, `write-implementation-review`, `write-accepted-task-result`, or `write-final-workflow-review`; bounded task amendment uses `amend-task`. Apply the single `orch-artifact-authoring` policy: no direct canonical YAML/Markdown creation/editing, including malformed-active bootstrap repair. Target-affecting identity/path/lifecycle/binding/current-state conflicts refuse before mutation. An applied valid target with unrelated invalid siblings may report `index_effect: stale` and exact `index_diagnostics`; repair each sibling through its own writer and rebuild the family projection. This outcome does not issue a product verdict or authorize direct edits. Unregistered specialized reader documents retain their existing owner.

## Specification

The agent authors complete specification semantics. The schema-backed writer owns structural fields, canonical location, immutable family identity, lifecycle movement, and index projection. A distinct reviewer advises on user-purpose alignment, authority, requirement/constraint/interface/acceptance coverage, conflicts, open questions, and scope. The controller/orchestrator assesses that advice and owns specification qualification.

## Planning

The agent authors root-plan, phase, and task semantics from a verified specification. Each artifact cites exact source IDs. The plan assigns ownership, dependencies, write scopes, task-local methodology, validation capability, and completion criteria. Static admission may report structural and graph facts but cannot qualify the plan. A distinct reviewer advises on the accuracy, completeness, decomposition, and executability of the complete current tree for initial/global qualification or the complete affected authority closure for a bounded repair; the controller/orchestrator assesses that advice and owns qualification.

Repair current plan content at the existing canonical plan, phase, and task identities. Do not create active copies for intermediate review revisions. Return a verified plan to draft before child-content repair. A bounded task repair refreshes only the amended task's compiled brief, preserves unaffected qualified regions and briefs, and reviews the complete affected authority closure against its allocated specification obligations and bounded source evidence. A textual-delta-only check cannot qualify repaired content; a global root-plan or cross-plan-authority repair still requires complete-tree review.

Form the smallest sufficient development runtime from current named obligations. Omit, substitute, or defer burdens that do not improve the current outcome or capable local oracle, and exclude release-only work unless a current obligation requires it. Do not optimize task or phase cardinality. Every authoritative production path needs one production owner, but that responsibility may contain multiple dependency-ordered bounded execution packets. Start from the accepted outcome and capable local oracle; use evidenced source neighborhoods, dependencies, validation loops, review boundaries, and repair frontiers to choose one coherent task, ordered tasks with usable accepted intermediate results, or contract-decoupled parallel tasks against a stable boundary. Keep inseparable work together. Ask whether a likely change or failure stays inside each packet and whether its result can be verified without unfinished siblings. Weigh expected total orchestration cost across execution, context, coordination, validation, review, and repair, alongside demonstrated reuse, feasibility, and stability. Task-size metrics are diagnostic, not gates. Keep a coherent mechanical increment with one owner, oracle, and repair frontier together. Create phases only for an actual barrier, convergence boundary, or coherent user-evaluable capability boundary. Reject speculative splits, and reshape a preparation-only non-final phase into the capability it enables or merge it into its consumer. When a task is materially under-decomposed, return to the plan and reslice only the affected unaccepted authority region; do not repeatedly enlarge it.

Apply an obligation-versus-cost comparison, not a score: retain every necessary product component and operational step even when expensive. Use a stable optional boundary only when practical and beneficial; do not manufacture it when its coordination cost exceeds its current benefit. Use the cheapest capable early probe before a costly compile, startup, or integration step when it can falsify a consequential assumption.

Consider independently changing policy and adapters only when the change axis is evidenced. For a consequentially uncertain interface, a small walking vertical slice with an observable result and capable local test may settle the boundary at reasonable cost. At a genuine stable parallel seam, an existing interface may suffice; local contract tests may provide useful oracles, with joint validation after convergence. Work sequentially while the seam is unsettled. These are conditional controller judgment prompts, not a pattern checklist, score, contract-first requirement, extra review round, or new qualification gate. Overlapping write paths require strict dependency order and the predecessor's canonical accepted result before successor execution; unordered overlap cannot run concurrently.

Disposable task briefs and lightweight development plans compile accepted authority for execution. They are not durable semantic authority.

## Execution and executor results

Executors work only within bound task/repository/write scope. Behavior changes use task-local methodology and claim-relevant focused validation. Executors report facts; they never accept the product.

After execution, create one canonical `executor-result-v2` under the catalog-selected result location. It records implemented scope, changed paths, focused validation observations, unresolved product blockers, task fit, repository/CodeGraph facts, delegation, and knowledge disposition. Necessary structural and binding checks occur before mutation. Repair the active result at the same identity; do not retain intermediate revision copies. Historical handoffs, embedded statuses, override sidecars, and fallback indexes are unsupported and ignored.

For a designated phase delivery task, first publish one immutable canonical runtime bundle, then record factual `phase_handoff` identity, bridge observations, complete `--all` rows, reproduction instructions and limitations. Prewrite acceptance checks current phase predecessors and executor result, exact bundle/product/manifest/bridge identities and passing required observations/report; the controller owns the semantic decision. The ordinary delivery-task accepted result is the only cross-phase continuation token. Surface its snapshot asynchronously without a phase reviewer, receipt or user wait state. Later user findings return to the affected authority closure; preserve unrelated accepted work and reuse observations only with unchanged exact phase/task, product, manifest, command, scope and freshness identities.

## Direct implementation review

Freeze an exact commit or worktree candidate using a path-sorted changed-path manifest. For a task review, a distinct reviewer compares the actual candidate with the complete current task authority closure—named specification requirements/decisions, applicable root/phase authority, complete task/dependencies, accepted dependency results, connected ownership/interfaces, edge/failure behavior, and capable focused observations. An integrated review compares the exact candidate with every planned feature and acceptance obligation in the complete plan tree.

`build-implementation-review-candidate --kind commit` requires `--candidate-commit` (`candidate_commit` in the builder API) to identify the reviewed commit bytes. `--kind worktree` requires `--base-commit` (`base_commit` in the API) for the real worktree baseline and deleted-path admission. Supply exactly the input for the selected kind; the baseline option is not a commit-mode alias. Supported persisted v2/v3 targets retain `target.base_commit`: it stores the candidate commit in commit mode and the baseline in worktree mode. Current readers select the corresponding builder argument without rewriting active records.

The reviewer issues an advisory `accept`, `repair`, or `blocked` assessment from product correctness. Passing tests cannot hide missing behavior. Missing or defective historical artifacts, indexes, knowledge state, or controller ceremony are separate supporting-state defects unless they make the product ambiguous, unsafe, inaccessible, or impossible to review. Store new or repaired advice in the current canonical `implementation-review-v3`; task review freshness uses a source-addressed task authority closure—referenced specification semantics, applicable root/phase authority, complete task/dependencies and accepted dependency results, and connected ownership/interfaces—while integrated review freshness uses the complete plan tree. Unrelated specification prose, source records, plan allocation, or phase membership do not invalidate a task review. The current reader admits already-active v2 reviews without rewriting or replaying them so unrelated accepted work remains usable. Its `verdict` field is a recommendation, not orchestration authority. A complete re-review after repair updates that active identity instead of retaining intermediate verdict copies.

Reviewer execution may use read-only workspace isolation and transient provider diagnostics. Those operational facts do not become semantic or lifecycle authority and are not replayed by downstream consumers.

## Accepted continuation

After assessing the implementation review advice, the controller/orchestrator either routes repair/blocking or creates one canonical `accepted-task-result-v2`. It references the exact executor result, implementation review advice when required, current task-authority identity, validation outcomes, product identity, unresolved material defects, and knowledge disposition. Repair its active identity in place. Dependencies and final review consume this compact controller decision without redispatching the executor or reconstructing review history. The current reader admits already-active v1 results without rewriting unrelated work; all new or repaired results use v2.

## Final workflow review

A distinct final auditor performs one compact advisory pass over plan/task coverage, controller-accepted implementation decisions, relevant current tests, unresolved material defects, final knowledge disposition/return, repository finalization facts, and truthful archive readiness. The auditor does not reread source for code quality or repeat implementation review. The controller/orchestrator assesses that advice and owns the closure decision.

Store or repair the controller/orchestrator closure decision at one active canonical `final-workflow-review-v1` identity. Deterministic finalization carries that supplied decision and validates only canonical references, lifecycle state, clean baselines, archive destinations, index rebuilds, and binding release. Mechanical failure cannot manufacture or reinterpret a semantic decision.

Finalization checks every accepted bundle cleanup target read-only before deleting any payload. Live/uncertain leases, mismatches and unexplained absence block it; dead runners require verified bounded child/external cleanup. The exact release owner retains identity-bound cleaning/cleaned states on partial failure. Retry validates the same accepted handoff and exact current active/archived chain, archives only after all cleanup, then removes temporary state/root. Explicit earlier release leaves matching cleaned state; preacceptance release uses persisted materialization identity and permits repaired rematerialization. Stale accepted references never fall back to candidate authority. Lifecycle advancement alone does not replay expensive current observations.

The plan-bound final workflow record's `accepted_reviews` references exact task reviews carried by accepted task results. Its writer also attaches current integrated implementation reviews matching the same plan and final candidate, validating those references before storage. An integrated review remains plan-scoped, never masquerades as a task review, and does not change the plan's semantic identity or create an acceptance gate. Finalization archives each referenced current review with the plan.

## Knowledge disposition

Each meaningful validated move records `none`, `update`, `supersede`, or `reclassify`. Approved persistence is delegated to the appropriate `ks-*` owner. Orchestration never writes durable knowledge directly, and supporting knowledge state does not determine product qualification.

## Current command surface

- `scaffold`
- `build-task-brief`
- `write-executor-result`, `list-executor-results`, `transition-executor-result`, `index-executor-results`
- `build-implementation-review-candidate`
- `write-implementation-review`, `list-implementation-reviews`
- `write-accepted-task-result`, `list-accepted-task-results`
- `write-final-workflow-review`, `list-final-workflow-reviews`
- `finalize-reviewed-plan`

Legacy orchestration handoff, executor validation/adoption, review-history, and legacy finalization commands are unsupported.

The current catalog accepts result/review ID shapes `result-[a-z0-9][a-z0-9-]*`, `review-[a-z0-9][a-z0-9-]*`, `accepted-[a-z0-9][a-z0-9-]*`, and `final-[a-z0-9][a-z0-9-]*`. After the family prefix, use a lowercase letter or digit followed by zero or more lowercase letters, digits, or hyphens; dates and revision suffixes are optional.

`scaffold --family <family>` emits a read-only semantic-input envelope for precisely `specification-v1`, `plan-v1`, `phase-v2`, `task-v3`, `executor-result-v2`, `implementation-review-v3`, `accepted-task-result-v2`, and `final-workflow-review-v1`. Supply canonical parent bindings (`--source-spec-id` for a new root plan, `--plan-id` for descendants/reviews/results, `--phase-id` for a task, and an existing `--task-id` for task-bound results/reviews). For example, `scaffold --family task-v3 --plan-id plan-example --phase-id phase-example --task-id task-new --source-id REQ-001` resolves that named unit from the plan's active verified specification.

The output keeps writer CLI options in `invocation_inputs`, editable keys/placeholders in `semantic_input`, canonical source facts/prose in read-only `resolved_context`, and the actual reader's structural restrictions in `script_owned_fields`. Explicitly fill each placeholder and send only the semantic payload to the named writer; specification front matter also uses the filled `semantic_body`. Scripts validate identities and reference existence before output. They do not synthesize decomposition, obligation prose, verdicts, qualification, or acceptance, and scaffolding never writes canonical artifacts or automatically supports new catalog families.

An implementation-review scaffold exposes the persisted target's `kind`, `base_commit`, `manifest`, and `sha256` as semantic input placeholders. The agent supplies the exact candidate target and authors the review; the scaffold does not build the target or generate product review or acceptance.
