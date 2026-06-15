---
name: orch-doctor
description: 'Run read-only develop-rules and orchestrator workflow diagnostics.'
---

# orch-doctor

## Scope

Run read-only develop-rules and orchestrator workflow diagnostics.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/orchestration/doctor.md` for directive-specific behavior.

## Runtime Rules

- `orch-doctor-readonly`: `rules/orchestration/orch-doctor-readonly.md`

## Rule Loading (mandatory)

Before directive-specific work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive orchestration work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or directive summaries as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress orchestration task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Read-Only Constraints (skill-owned)

Diagnose develop-rules installation health and orchestrator workflow consistency without mutating project files, orchestration artifacts, or durable knowledge. Doctor collects independent findings and reports concrete repair actions.

### Must

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

### Must Not

- Edit, repair, rewrite, delete, archive, or generate orchestration artifacts during doctor.
- Mutate source files, project files, durable knowledge, indexes, or configuration as part of diagnosis.
- Duplicate or replace `dev-rules-doctor` installation, registry, front matter, or symlink checks.
- Inspect `.work-bundle/knowledge/` or unrelated project files unless the user explicitly expands diagnosis scope.
- Apply fixes directly instead of reporting recommended repairs.

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Boundary

Platform write boundary and durable-knowledge prohibition: follow `orch-orchestration-boundary` (`rules/orchestration/orch-orchestration-boundary.md`).
