---
id: orch-artifact-authoring
applies_when:
  - an orchestration artifact is created or validated
  - a specification, plan, phase, task, executor result, implementation review, accepted task result, final workflow review, or orchestration document is authored or repaired
enforcement: must
load: conditional
requires: []
---

# Orchestration Artifact Authoring

## Purpose

Keep orchestration artifacts human-readable, contract-compliant, and executable without loading unrelated reference material or duplicating specification prose across the execution chain.

## Must

- Require every executable task to declare the five-field Truth Basis. Decision authority is semantically distinct from generic source IDs and must be `none-relevant` or an `AUTH-NNN` alias allocated in order from a verified specification's accepted `source_knowledge`. Compiled briefs and review packages receive the same resolved `AUTH-NNN: <carried constraint>` values so executors can obey the authority without knowledge paths or rediscovery.
- Put the earliest ordinary falsification task before broad simplification when a consequential assumption exists; do not create a separate checkpoint lifecycle.

- Load only the directive contract and template references required for the artifact being created or validated.
- For a family registered in the maintained artifact-family catalog, supply the semantic payload to the shared artifact store and let that structural owner select the immutable schema, validate identity and declared bindings, resolve the canonical anchor/path, serialize, mutate atomically, apply location-owned lifecycle mechanics, and project any derived index. Structural success is evidence only; the responsible agent still owns semantic correctness, sufficiency, qualification, review, and acceptance.
- Treat registration as an owning-stage cutover. Until a specialized artifact family has a real immutable schema and complete structural policy, keep its current owner and reject it through the shared store; do not add permissive placeholder entries, fallback identities, sidecars, or compatibility authority.
- Search directories only when retrieval, index rebuilding, navigation, or diagnostics is the declared operation. Treat every hit as a candidate until maintained parsing, schema validation, and canonical-location checks succeed; neither a hit nor a passing structural check establishes semantic authority.
- Use the registered representation for each current family: human-readable Markdown/front matter for specifications and schema-owned YAML for root plans, phases, tasks, executor results, implementation reviews, accepted task results, and final workflow reviews. Do not create Markdown plan/phase/task compatibility copies or other Markdown compatibility copies for YAML families.
- Reference stable spec IDs such as `REQ-`, `CON-`, `AC-`, `OQ-`, and `API-` in plans, phases, and tasks instead of repeating full requirement prose.
- Provide concrete source files, target files, target symbols, validation instructions, and completion criteria in every task.
- Carry execution context forward through spec-ID references plus file-level instructions only.
- Do not optimize task or phase cardinality. Start from the accepted outcome and capable local oracle, then choose coherent bounded execution packets at evidenced source-neighborhood, dependency, validation, review, or repair seams. Bound expected total orchestration cost across execution, context, coordination, validation, review, and repair while preserving Truth Basis continuity, independently falsifiable increments, short evidence loops, and complete source-spec coverage. Task-size metrics are diagnostic clues, not qualification thresholds.
- Assign every authoritative production path to one production owner. Responsibility ownership does not require one task: the same owner may have ordered bounded tasks, including ordered reuse of a production file. Reject helper-only allocation while a production path is unowned, and keep a coherent mechanical increment with one owner, oracle, and repair frontier together. Split only when the intermediate result is usable and reviewable; keep inseparable work together.
- For each proposed packet, ask whether a likely change or failure stays inside it and whether a capable local oracle verifies its result without unfinished siblings. Consider independently changing policy and adapters, a small observable walking vertical slice for a consequentially uncertain interface, or local contract tests at a genuinely stable parallel seam only when current evidence and total cost support them. Use an existing stable interface when sufficient; do not require a new contract artifact, design pattern, checklist, score, or qualification gate.
- Create phases only for an actual barrier or convergence boundary. Reject speculative splits unsupported by current authority, repository, dependency, ownership, validation, or acceptance evidence.
- When execution proves a task materially under-decomposed, return to the plan and reslice only the affected unaccepted authority region while preserving the original binding, baseline, and accepted unaffected regions; do not repeatedly enlarge the task.
- Bind review freshness to one canonical semantic plan projection shared by all consumers. Status-only lifecycle fields and append-only evidence references do not change that projection; requirements, scope, dependencies, validation allocation, acceptance, or authority changes do.
- Keep pre-execution artifact revision separate from bounded post-execution review: plan and specification revisions do not consume post-execution review rounds. Do not encode a plan-version or specification-version counter as execution policy.
- Run the compiler's canonical static task admission for every plan task before plan acceptance so missing dependencies, inconsistent authority, unsafe scope, and source-local execution artifacts fail before execution.
- When plans contain contract-decoupled parallel tasks, use a sufficiently stable existing or task-produced common boundary and include applicable common contract groups, barrier participant maps, readiness criteria, release conditions, convergence owners, and task-level forbidden peer validation instructions. Place joint validation after convergence; work sequentially while the boundary is unsettled. Strictly order overlapping write paths and require the predecessor's canonical accepted result before successor execution; reject unordered overlap.
- Keep source-context, extra-evidence-loop, open-question, Knowledge Base Update, and body-level `Quality gate: verified|blocked` sections in specifications when required by the specification contract.
- Summarize spec intent at most once in a root plan, then cite IDs for downstream detail.
- Require leading spec-repair tasks when a phase or task lacks stable IDs, exact paths, validation details, or file-level execution context.
- Let the shared store rebuild the distinct per-family indexes when registered artifacts change; derived indexes are projections and do not replace canonical artifacts.
- Update an active orchestration artifact at its existing canonical identity when repairing its content. Allocate a new identity only for a genuinely distinct semantic artifact, not for an intermediate review revision. Transitioned historical records remain immutable.
- Use the focused `amend-task` operation for a bounded task repair so deterministic structure, binding, dependency, allocation, ownership, and candidate compilation are checked before mutation; treat its affected-task report as evidence for controller impact judgment, not as qualification authority.
- For initial plan qualification and any global root-plan repair, require the distinct reviewer to assess the complete current canonical tree, including packet coherence, boundedness, and genuine separability. For a bounded phase or task repair, preserve unaffected qualified authority and require review of the complete affected authority closure: the repaired artifact, its applicable root/phase authority, dependency closure, affected interfaces, and exact specification requirements/decisions named by that closure's source IDs. Use the existing full-plan or affected-closure review, without an extra per-task invocation. Unrelated specification prose, source records, plan allocation, or phase membership do not invalidate unaffected authority. The controller/orchestrator decides the semantic impact boundary, evaluates the advice, and owns qualification. A textual-delta-only check does not qualify a repaired artifact.
- Keep controller/orchestrator authority explicit when an artifact records review or continuation: review remains advisory, accurate findings are assessed and routed by the controller/orchestrator, and a suggestion cannot silently expand scope or authorize delivery.

Contract loading by artifact type:

| Artifact | Load when creating or validating |
| --- | --- |
| Specification | `specification-v1.md` |
| Root plan | `plan-v1.md` |
| Phase | `phase-v1.md` |
| Task | `task-v1.md` |
| Executor result | `handoff-executor-result-v1.md` |

## Must Not

- Inline unrelated long contracts, examples, or reference corpora into orchestration artifacts.
- Repeat full requirement prose in plans, phases, or tasks when a spec-ID reference suffices.
- Omit source files, target files, target symbols, validation rules, or completion criteria from executable tasks.
- Use broad globs such as `src/**` as the only source or target path without exact files or narrow symbol-level explanation.
- Do not reslice a plan or request a fresh plan review for status-only or append-only evidence changes.
- Split phases or tasks solely because of template habit, lifecycle labels, duplicated prose, a task-count target, or another cardinality preference when the coherent artifact remains complete and executable.
- Encode sibling in-progress implementation files as dependencies for contract-decoupled parallel task validation; use common contracts, accepted prior executor results, and post-barrier convergence instead.
- Use a legacy plan-version limit field in a current specification, plan, phase, or task, or describe artifact revisions as post-execution review rounds.
- Create phases or tasks whose target files are `.work-bundle/knowledge/**`.
- Embed implementation plan tasks inside specifications.
- Write raw chat logs, unsupported facts, or hidden reasoning into orchestration artifacts.
- Infer artifact identity, lifecycle state, relationships, or acceptance from filenames, headings, search order, or fallback defaults when a registered structural contract owns those facts.
- Preserve intermediate repair versions as additional active canonical artifacts or qualify repaired content from a review limited to changed fields.

## Validation

- Confirm only the required contract files for the active artifact type were loaded.
- Confirm plans, phases, and tasks cite relevant spec IDs and include concrete file-level execution instructions.
- Confirm decomposition is explicitly checked, every authoritative production path has one production owner, and each task is a coherent bounded packet. A split may retain that owner when a current dependency, validation, review, repair-frontier, barrier, or convergence seam makes the intermediate result usable and reviewable; common ownership or a dependency edge alone is insufficient.
- Confirm contract groups, barrier metadata, convergence tasks, and forbidden peer validation appear where parallel tasks share a common contract.
- Confirm no phase or task repeats more than a short one-line requirement summary without a spec-ID reference.
- Confirm task files are self-contained for execution from the related spec plus their own instructions.
- Confirm artifact sections satisfy the loaded contract or explicitly add missing required sections named by the directive.
- Confirm registered families use the shared structural owner, unregistered families have not gained placeholder authority, and any search is both declared and followed by canonical structural validation.
- Confirm plan semantic qualification came from the controller/orchestrator's assessment of distinct-agent advice on specification coverage, ownership, dependencies, validation, authority, scope, and executability; neither the reviewer recommendation nor structural checks and supporting ceremony issued the qualification automatically.
- Confirm repaired artifacts retained their canonical identities, the complete affected authority closure—not merely its textual delta—received independent review, unaffected qualified regions were preserved, and the controller/orchestrator assessed that advice before qualification.

## On Violation

Stop artifact authoring, load the minimal required contracts, repair the artifact to use spec-ID references and concrete source/target/validation detail, and reject duplicated specification prose before continuing.
