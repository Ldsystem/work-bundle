---
id: orch-doctor-readonly
applies_when:
  - user invokes orch-doctor or the doctor directive
  - orchestrator read-only diagnostics are requested
enforcement: must
load: conditional
requires: []
---

# Orchestration Doctor Read-Only

## Purpose

Diagnose develop-rules installation health and orchestrator workflow consistency without mutating project files, orchestration artifacts, or durable knowledge. Doctor collects independent findings and reports concrete repair actions.

## Must

- Run the builtin `dev-rules-doctor` skill first through `$DEV_RULES_HOME/scripts/dev-rules doctor`.
- Stop and report the blocker if `dev-rules-doctor` cannot run; do not treat installation health as passed.
- Perform a read-only orchestrator audit across orchestrator skill files, workflow reference, orchestration directives, orchestration evals, and helper commands in `scripts/orch.py`.
- Verify directive coverage, front matter consistency, workflow responsibility separation, retrieval-policy mappings, helper command availability or declared fallback behavior, and required execution fallback paths.
- Verify `execute-plan` checks sub-agent support, preserves single-agent fallback, and does not archive artifacts during execution.
- Verify `review-plan` is the only directive that archives completed specification, plan, and handoff artifacts.
- Verify knowledge-using directives route through `keep-summarizing` rather than direct `.work-bundle/knowledge/` browsing.
- Look for workflow bias such as mandatory sub-agents when unavailable, skipped handoffs, execution treated as review, or handoff conclusions treated as persisted knowledge.
- Report findings as concrete repair actions with cited conflicting artifacts when issues are found.
- Emit doctor output with `Files changed: none`.

## Must Not

- Edit, repair, rewrite, delete, archive, or generate orchestration artifacts during doctor.
- Mutate source files, project files, durable knowledge, indexes, or configuration as part of diagnosis.
- Duplicate or replace `dev-rules-doctor` installation, registry, front matter, or symlink checks.
- Inspect `.work-bundle/knowledge/` or unrelated project files unless the user explicitly expands diagnosis scope.
- Apply fixes directly instead of reporting recommended repairs.

## Validation

- Confirm `dev-rules-doctor` ran first and its results were included in the report.
- Confirm all diagnostics remained read-only and no files were changed.
- Confirm directive set consistency, workflow integrity, and bias checks were performed.
- Confirm output states `Files changed: none` and lists recommended repairs or `none`.

## On Violation

Stop the doctor run, report that file mutation or skipped installation diagnostics occurred, and rerun doctor in read-only mode with `dev-rules-doctor` first before presenting results.
