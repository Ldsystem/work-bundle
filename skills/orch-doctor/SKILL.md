---
name: orch-doctor
description: 'Run read-only develop-rules and orchestrator workflow diagnostics.'
---

# orch-doctor

## Scope

Run read-only develop-rules and orchestrator workflow diagnostics.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

This skill is read-only and must not repair, rewrite, delete, archive, or generate orchestration artifacts.

## Required Skill

Use the builtin `dev-rules-doctor` skill first. Do not duplicate or replace its installation, registry, front matter, or symlink checks.

Run:

```text
$DEV_RULES_HOME/scripts/dev-rules doctor
```

Explain any reported issue as a concrete repair action. If the command cannot run, report the blocker and do not continue as if installation health passed.

## Orchestrator Audit Scope

After `dev-rules-doctor` completes, perform a read-only orchestrator-specific audit across:

- `skills/orch-*/SKILL.md`;
- `references/assets/orchestration/workflow.md`;
- `references/evals/orchestration/evals.json`;
- helper commands in `scripts/orch.py`.

Do not inspect `.work-bundle/knowledge/`. Do not inspect unrelated project files unless the user explicitly expands the diagnosis scope.

## Consistency Checks

Verify:

1. every `orch-*` skill listed in the workflow reference has a matching `skills/orch-*/SKILL.md` file;
2. every orch skill file has front matter with `name` and `description`;
3. front matter `name` matches the skill directory name;
4. workflow reference and evals describe the same orch skill set;
5. helper commands mentioned by orch skills exist or the skill clearly states the fallback behavior;
6. no orch skill instructs agents to write outside `.work-bundle/orchestration/` except source/test changes allowed by `orch-execute-plan`;
7. no orch skill instructs agents to read `.work-bundle/knowledge/` directly when knowledge must go through `keep-summarizing`.
8. every knowledge-using orch skill has a retrieval policy mapping or an explicit no-retrieval rule;
9. `keep-summarizing` `what-is-helpful` documents gateway mode, `ks.py query`, and `authority | candidate | background | blocked` retrieval roles;
10. keep-summarizing active docs do not advertise legacy note paths or `archived` note status;
11. orchestration evals that require v3 role labels are backed by orch skill documentation.

## Workflow Integrity Checks

Verify:

- `orch-create-specification`, `orch-create-implementation-plan`, `orch-create-handoff`, `orch-execute-plan`, `orch-review-plan`, and `orch-doctor` keep distinct responsibilities;
- artifact creation modes do not execute implementation work;
- `orch-execute-plan` checks sub-agent support before delegation;
- `orch-execute-plan` preserves the single-agent fallback and does not fail only because sub-agents are unavailable;
- `orch-execute-plan` does not archive specs, plans, or handoffs;
- `orch-review-plan` is the only skill that archives completed specification, plan, and handoff artifacts;
- `orch-review-plan` creates a repair specification instead of fixing source files when review fails;
- `orch-doctor` stays read-only and reports repair instructions instead of applying them.

## Bias Checks

Look for one-sided or conflicting instructions that would bias execution toward a single path when alternatives are required:

- sub-agent scheduler must not be mandatory when sub-agents are unavailable or unsafe;
- single-agent fallback must not silently bypass required handoffs or status updates;
- review must not be treated as execution;
- execution completion must not imply archival;
- durable knowledge extraction must not be implied by orchestration handoffs.

When bias is found, cite the conflicting artifact and the exact behavior risk.

## Output

```text
Doctor result: passed|issues-found|blocked
dev-rules doctor:
- <passed or issue summary>
Orchestrator consistency:
- <passed or issue summary>
Workflow integrity:
- <passed or issue summary>
Bias checks:
- <passed or issue summary>
Recommended repairs:
- <concrete repair action or none>
Files changed: none
```

## Validation

Confirm `dev-rules-doctor` was used first, diagnostics stayed read-only, orch skill coverage was checked, skill front matter was checked, workflow responsibilities remained distinct, required fallback paths were present, archival remained isolated to `orch-review-plan`, and no files were changed.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`

## Rule Loading (mandatory)

Before substantive doctor work, read **every** rule listed in **Runtime Rules** from disk in full.

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
- Perform a read-only orchestrator audit across orchestrator skill files, workflow reference, orchestration evals, and helper commands in `scripts/orch.py`.
- Verify skill coverage, front matter consistency, workflow responsibility separation, retrieval-policy mappings, helper command availability or declared fallback behavior, and required execution fallback paths.
- Verify `orch-execute-plan` checks sub-agent support, preserves single-agent fallback, and does not archive artifacts during execution.
- Verify `orch-review-plan` is the only skill that archives completed specification, plan, and handoff artifacts.
- Verify knowledge-using orch skills route through `keep-summarizing` rather than direct `.work-bundle/knowledge/` browsing.
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
