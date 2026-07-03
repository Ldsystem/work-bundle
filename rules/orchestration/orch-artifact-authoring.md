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

- Load only the directive contract and template references required for the artifact being created or validated.
- Use human-readable Markdown for specifications, plans, phases, tasks, handoffs, and orchestration documents; keep compact YAML to front matter and index files where contracts require it.
- Reference stable spec IDs such as `REQ-`, `CON-`, `AC-`, `OQ-`, and `API-` in plans, phases, and tasks instead of repeating full requirement prose.
- Provide concrete source files, target files, target symbols, validation instructions, and completion criteria in every task.
- Carry execution context forward through spec-ID references plus file-level instructions only.
- Keep generated plans compact: use the fewest phases and tasks that preserve complete source-spec coverage, explicit dependencies, disjoint write scopes, validation ownership, handoff requirements, and review gates.
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
- Split phases or tasks solely because of template habit, lifecycle labels, or duplicated prose when a smaller artifact remains complete and executable.
- Encode sibling in-progress implementation files as dependencies for contract-decoupled parallel task validation; use common contracts, accepted prior handoffs, and post-barrier convergence instead.
- Create phases or tasks whose target files are `.work-bundle/knowledge/**`.
- Embed implementation plan tasks inside specifications.
- Write raw chat logs, unsupported facts, or hidden reasoning into orchestration artifacts.

## Validation

- Confirm only the required contract files for the active artifact type were loaded.
- Confirm plans, phases, and tasks cite relevant spec IDs and include concrete file-level execution instructions.
- Confirm compactness is explicitly checked, and any phase/task split is justified by distinct write scope, dependency, validation ownership, risk, barrier participation, or convergence ownership.
- Confirm contract groups, barrier metadata, convergence tasks, and forbidden peer validation appear where parallel tasks share a common contract.
- Confirm no phase or task repeats more than a short one-line requirement summary without a spec-ID reference.
- Confirm task files are self-contained for execution from the related spec plus their own instructions.
- Confirm artifact sections satisfy the loaded contract or explicitly add missing required sections named by the directive.

## On Violation

Stop artifact authoring, load the minimal required contracts, repair the artifact to use spec-ID references and concrete source/target/validation detail, and reject duplicated specification prose before continuing.
