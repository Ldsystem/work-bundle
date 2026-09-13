---
id: orch-artifact-authoring
applies_when:
  - an orchestration artifact is created or validated
  - a specification, plan, phase, task, handoff, or orchestration document is authored or repaired
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
- Use human-readable Markdown for specifications, plans, phases, tasks, handoffs, and orchestration documents; keep compact YAML to front matter and index files where contracts require it.
- Reference stable spec IDs such as `REQ-`, `CON-`, `AC-`, `OQ-`, and `API-` in plans, phases, and tasks instead of repeating full requirement prose.
- Provide concrete source files, target files, target symbols, validation instructions, and completion criteria in every task.
- Carry execution context forward through spec-ID references plus file-level instructions only.
- Do not optimize task or phase cardinality. Bound expected total orchestration cost by decomposing only at concrete independently owned production, dependency, validation, review, and repair seams while preserving Truth Basis continuity, independently falsifiable increments, short evidence loops, and complete source-spec coverage.
- Assign every authoritative production path to a production owner. Reject helper-only allocation while a production path is unowned, and keep a coherent mechanical increment with one owner, oracle, and repair frontier together.
- Create phases only for an actual barrier or convergence boundary. Reject speculative splits unsupported by current authority, repository, dependency, ownership, validation, or acceptance evidence.
- When execution proves a task materially under-decomposed, return to the plan and reslice only the affected region while preserving the original binding, baseline, and accepted unaffected regions; do not repeatedly enlarge the task.
- Bind review freshness to one canonical semantic plan projection shared by all consumers. Status-only lifecycle fields and append-only evidence references do not change that projection; requirements, scope, dependencies, validation allocation, acceptance, or authority changes do.
- Keep pre-execution artifact revision separate from bounded post-execution review: plan and specification revisions do not consume post-execution review rounds. Do not encode a plan-version or specification-version counter as execution policy.
- Run the compiler's canonical static task admission for every plan task before plan acceptance so missing dependencies, inconsistent authority, unsafe scope, and source-local execution artifacts fail before execution.
- When plans contain contract-decoupled parallel tasks, include common contract groups, barrier participant maps, readiness criteria, release conditions, convergence owners, and task-level forbidden peer validation instructions.
- Keep source-context, extra-evidence-loop, open-question, Knowledge Base Update, and body-level `Quality gate: verified|blocked` sections in specifications when required by the specification contract.
- Summarize spec intent at most once in a root plan, then cite IDs for downstream detail.
- Require leading spec-repair tasks when a phase or task lacks stable IDs, exact paths, validation details, or file-level execution context.
- Update plan, phase, and handoff indexes when artifacts change.

Contract loading by artifact type:

| Artifact | Load when creating or validating |
| --- | --- |
| Specification | `specification-v1.md` |
| Root plan | `plan-v1.md` |
| Phase | `phase-v1.md` |
| Task | `task-v1.md` |
| Orchestration handoff | `handoff-orchestration-v1.md` |
| Executor-result handoff | `handoff-executor-result-v1.md` |

## Must Not

- Inline unrelated long contracts, examples, or reference corpora into orchestration artifacts.
- Repeat full requirement prose in plans, phases, or tasks when a spec-ID reference suffices.
- Omit source files, target files, target symbols, validation rules, or completion criteria from executable tasks.
- Use broad globs such as `src/**` as the only source or target path without exact files or narrow symbol-level explanation.
- Do not reslice a plan or request a fresh plan review for status-only or append-only evidence changes.
- Split phases or tasks solely because of template habit, lifecycle labels, duplicated prose, a task-count target, or another cardinality preference when the coherent artifact remains complete and executable.
- Encode sibling in-progress implementation files as dependencies for contract-decoupled parallel task validation; use common contracts, accepted prior handoffs, and post-barrier convergence instead.
- Use a legacy plan-version limit field in a current specification, plan, phase, or task, or describe artifact revisions as post-execution review rounds.
- Create phases or tasks whose target files are `.work-bundle/knowledge/**`.
- Embed implementation plan tasks inside specifications.
- Write raw chat logs, unsupported facts, or hidden reasoning into orchestration artifacts.

## Validation

- Confirm only the required contract files for the active artifact type were loaded.
- Confirm plans, phases, and tasks cite relevant spec IDs and include concrete file-level execution instructions.
- Confirm decomposition is explicitly checked, every authoritative production path has a production owner, and any phase/task split is justified by a current dependency, ownership, validation, review, repair-frontier, barrier, or convergence seam.
- Confirm contract groups, barrier metadata, convergence tasks, and forbidden peer validation appear where parallel tasks share a common contract.
- Confirm no phase or task repeats more than a short one-line requirement summary without a spec-ID reference.
- Confirm task files are self-contained for execution from the related spec plus their own instructions.
- Confirm artifact sections satisfy the loaded contract or explicitly add missing required sections named by the directive.

## On Violation

Stop artifact authoring, load the minimal required contracts, repair the artifact to use spec-ID references and concrete source/target/validation detail, and reject duplicated specification prose before continuing.
