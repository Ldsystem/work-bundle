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
11. orchestration evals that require v3 role labels are backed by orch skill documentation;
12. specification and plan contracts allocate `dev-semantic-convergence`, caller-specific lenses, compact `semantic_loop` evidence, and the body-level `Quality gate: verified|blocked` result where applicable;
13. task contracts carry source IDs, methodology, provider-neutral capability, compiled-brief context, and acceptance-review fields;
14. execution contracts preserve no-retrieval execution, compile bounded task/review packets, require fresh task validation plus acceptance review, and keep reduced-independence fallback explicit;
15. the CodeGraph-first rule remains conditional on an indexed target and requires a recorded fallback reason when unavailable;
16. active orchestration contracts do not depend on `HABITS.md` or the deprecated role-selection subsystem.
17. executor-result contracts default to sparse YAML, require fields by applicability, reject forbidden executor advice fields, and do not require active orchestration handoffs;
18. compact CodeGraph evidence retains `root`, `applicable`, `up_to_date`, and required fallback or blocker facts, including `no-index` and `sync-failed` where applicable;
19. compact visible delegation evidence uses `delegation_evidence`, `visible_reference` when available, and `internal_spawn_used_for_task_delegation: false`;
20. no active orch contract reintroduces invisible internal spawn work as a valid task-delegation vehicle;
21. handoff and review contracts validate compact CodeGraph and visible delegation outcomes by applicability rather than fixed prose sections.

## Workflow Integrity Checks

Verify:

- `orch-create-specification`, `orch-create-implementation-plan`, `orch-create-handoff`, `orch-execute-plan`, `orch-review-plan`, and `orch-doctor` keep distinct responsibilities;
- artifact creation modes do not execute implementation work;
- `orch-execute-plan` checks sub-agent support before delegation;
- `orch-execute-plan` preserves the single-agent fallback and does not fail only because sub-agents are unavailable;
- layered `prefer_subagent` remains permission-only and cannot bypass preflight, dependency, scope, or handoff safety checks;
- executor-result handoffs require local task-fit evidence against the compiled brief and assigned task, with full lifecycle artifacts reserved for inconsistent context or source-contract escalation;
- executor-result handoffs default to sparse YAML, omit non-applicable fields, reject forbidden executor advice fields, and require compact `codegraph:` and `delegation_evidence:` only when applicable;
- active orchestration handoffs are unavailable and continuation uses active specs, plans, tasks, indexes, and executor-result handoffs;
- `orch-execute-plan` does not archive specs, plans, or handoffs;
- `orch-review-plan` is the only skill that archives completed specification, plan, and handoff artifacts;
- `orch-review-plan` routes implementation rejection to task repair/re-review, plan defects to plan repair, and requirement/design/authority defects to specification repair;
- `orch-doctor` stays read-only and reports repair instructions instead of applying them.

## Bias Checks

Look for one-sided or conflicting instructions that would bias execution toward a single path when alternatives are required:

- sub-agent scheduler must not be mandatory when sub-agents are unavailable or unsafe;
- single-agent fallback must not silently bypass required handoffs or status updates;
- review must not be treated as execution;
- execution completion must not imply archival;
- durable knowledge extraction must not be implied by executor-result handoffs;
- CodeGraph sync evidence must not be optional when `.codegraph/` exists and graph-derived source work is in scope;
- visible delegation wording must not allow invisible internal spawn work to own delegated plan, phase, or task execution.

Deterministic doctor checks are limited to bounded file presence, JSON shape,
required contract terms, and forbidden active dependencies. They must not judge
semantic evidence sufficiency, user-purpose drift, materiality, task code quality,
or whether semantic convergence needs another round.

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

Confirm `dev-rules-doctor` was used first, diagnostics stayed read-only, orch skill coverage was checked, skill front matter was checked, semantic-convergence and compiled-context terms were present, sparse YAML and applicability terms were present, forbidden executor advice fields and active orchestration handoffs were rejected, compact CodeGraph and visible delegation safety terms were present, invisible internal spawn task-delegation regressions were absent, forbidden active dependencies were absent, workflow responsibilities remained distinct, required fallback paths were present, archival remained isolated to `orch-review-plan`, and no files were changed.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`

Central `AGENTS.md` owns rule discovery and loading. Load the runtime rule above when its indexed condition applies.

## Read-Only Constraints (skill-owned)

Diagnose develop-rules installation health and orchestrator workflow consistency without mutating project files, orchestration artifacts, or durable knowledge. Doctor collects independent findings and reports concrete repair actions.

### Must

- Run the builtin `dev-rules-doctor` skill first through `$DEV_RULES_HOME/scripts/dev-rules doctor`.
- Stop and report the blocker if `dev-rules-doctor` cannot run; do not treat installation health as passed.
- Perform a read-only orchestrator audit across orchestrator skill files, workflow reference, orchestration evals, and helper commands in `scripts/orch.py`.
- Verify skill coverage, front matter consistency, workflow responsibility separation, retrieval-policy mappings, helper command availability or declared fallback behavior, and required execution fallback paths.
- Verify `orch-execute-plan` compiles bounded task/review packets, preserves visible sub-agent and reduced-independence fallback paths, requires fresh validation plus task acceptance, and does not archive artifacts during execution.
- Verify `orch-review-plan` is the only skill that archives completed specification, plan, and handoff artifacts.
- Verify knowledge-using orch skills route through `keep-summarizing` rather than direct `.work-bundle/knowledge/` browsing.
- Verify executor-result contracts default to sparse YAML, require fields by applicability, omit non-applicable fields, reject forbidden executor advice fields, and do not require active orchestration handoffs.
- Verify compact CodeGraph evidence includes `root`, `applicable`, `up_to_date`, and accepted fallback or blocker facts such as `no-index` and `sync-failed` where applicable.
- Verify compact visible delegation evidence uses `delegation_evidence`, `visible_reference` when available, and `internal_spawn_used_for_task_delegation: false`, and does not permit invisible internal spawn work to own delegated task execution.
- Look for workflow bias such as false review independence, skipped handoffs, scheduler-owned code review, mandatory full lifecycle context for a valid brief, or handoff conclusions treated as persisted knowledge.
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
