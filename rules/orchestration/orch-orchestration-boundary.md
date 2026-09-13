---
id: orch-orchestration-boundary
applies_when:
  - any orchestration artifact is created, updated, validated, or reviewed
  - an orch-* skill writes or validates content under .work-bundle/orchestration/
enforcement: must
load: conditional
requires: []
---

# Orchestration Platform Write Boundary

## Purpose

Define where orchestration artifacts live, how artifact roles stay separated across the execution chain, and how orchestration delegates durable knowledge work without taking ownership of durable knowledge writes.

Orchestration artifacts are derived working material under `.work-bundle/orchestration/`. Keep-summarizing owns durable project knowledge under `.work-bundle/knowledge/`.

## Must

- Write generated orchestration artifacts only under `.work-bundle/orchestration/`.
- permit cross-skill invocation scheduling or handoff to approved ks-* owners for durable knowledge work.
- Consume and validate delegated `ks-*` return evidence before treating durable knowledge work as complete.
- Keep specifications, plans, phases, tasks, handoffs, and reviews in distinct roles across the execution chain: `spec -> plan -> phase -> task -> execute -> handoff`.
- Preserve artifact role separation:

| Artifact | Role |
| --- | --- |
| **Specification** | Stable requirements, constraints, interfaces, acceptance criteria, alternatives, and open questions |
| **Root plan** | Execution strategy, sequencing, phase map, risk handling, validation strategy, and dependency graph |
| **Phase** | Bounded milestone grouping related tasks with only the spec IDs, decisions, files, and tests those tasks need |
| **Task** | One executable unit with exact source files, target files, symbols, steps, validation, completion criteria, and handoff requirements |
| **Handoff** | Executor or orchestration continuation evidence before advancing status |
| **Product review** | Independent judgment of one frozen product candidate against accepted product requirements and normalized observations |
| **Controller finalization** | Evidence admission, first-owner routing, lifecycle completion, and archive mechanics |

- Reference spec IDs in downstream plans, phases, and tasks instead of duplicating full requirement prose.
- Carry only task-specific execution detail in task files after citing stable spec IDs.
- After acceptance, make downstream orchestration consume the compact accepted result and current harness observations; keep transient acceptance evidence and historical handoff chains out of dependency, finalization, resume, and archive context.
- Route post-execution integrated review and closure through the canonical bounded controller. An exhausted flow refuses reconciliation before its blocker is written; an active workspace blocker refuses ordinary new work and unexempted reconciliation, while diagnosis and closure operations remain available.
- Keep normal accepted final audit/archive distinct from unresolved fifth-round forced closure. Controller mechanics own counting, admission, durable control state, and administrative retry; agents own product semantics and knowledge curation.

## Must Not

- Write orchestration artifacts under `.work-bundle/knowledge/`.
- directly create edit promote delete or index durable knowledge from orch-* skills.
- Store specifications, plans, phases, tasks, handoffs, or review outputs as durable knowledge notes.
- Duplicate full specifications inside plans or turn tasks into mini-specifications.
- Embed implementation plans inside specifications or make phase or task files read like new specifications.
- Perform orchestration artifact work from under the knowledge tree.
- Reconstruct accepted authority by replaying transient acceptance evidence or historical handoff chains after a compact accepted result is available.
- Bypass bounded admission by renaming an execution or reconciliation action as a read-only or closure operation.

## Validation

- Confirm every created or updated artifact path resolves under `.work-bundle/orchestration/`.
- Confirm artifact content matches its role in the execution chain and does not absorb another artifact's responsibilities.
- Confirm any durable knowledge request is delegated to an approved `ks-*` owner rather than written directly.
- Confirm plans, phases, and tasks cite spec IDs and concrete file-level instructions rather than repeating long requirement prose.

## On Violation

Stop the orchestration write, move or rewrite the artifact under the correct `.work-bundle/orchestration/` location and role, and delegate any durable knowledge work to the approved `ks-*` owner before continuing.
