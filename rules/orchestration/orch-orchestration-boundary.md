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
| **Review** | Final verification, repair-spec creation on failure, and archival on success |

- Reference spec IDs in downstream plans, phases, and tasks instead of duplicating full requirement prose.
- Carry only task-specific execution detail in task files after citing stable spec IDs.

## Must Not

- Write orchestration artifacts under `.work-bundle/knowledge/`.
- directly create edit promote delete or index durable knowledge from orch-* skills.
- Store specifications, plans, phases, tasks, handoffs, or review outputs as durable knowledge notes.
- Duplicate full specifications inside plans or turn tasks into mini-specifications.
- Embed implementation plans inside specifications or make phase or task files read like new specifications.
- Perform orchestration artifact work from under the knowledge tree.

## Validation

- Confirm every created or updated artifact path resolves under `.work-bundle/orchestration/`.
- Confirm artifact content matches its role in the execution chain and does not absorb another artifact's responsibilities.
- Confirm any durable knowledge request is delegated to an approved `ks-*` owner rather than written directly.
- Confirm plans, phases, and tasks cite spec IDs and concrete file-level instructions rather than repeating long requirement prose.

## On Violation

Stop the orchestration write, move or rewrite the artifact under the correct `.work-bundle/orchestration/` location and role, and delegate any durable knowledge work to the approved `ks-*` owner before continuing.
