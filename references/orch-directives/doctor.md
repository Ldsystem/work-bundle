---
name: doctor
description: 'Diagnose develop-rules installation health through dev-rules-doctor, then audit orchestrator directive consistency, workflow integrity, and workflow bias without editing files.'
---

# Doctor

Diagnose `${input:DoctorTarget}` for the orchestrator skill. This directive is read-only and must not repair, rewrite, delete, archive, or generate orchestration artifacts.

## Required Skill

Use the builtin `dev-rules-doctor` skill first. Do not duplicate or replace its installation, registry, front matter, or symlink checks.

Run:

```text
$DEV_RULES_HOME/scripts/dev-rules doctor
```

Explain any reported issue as a concrete repair action. If the command cannot run, report the blocker and do not continue as if installation health passed.

## Orchestrator Audit Scope

After `dev-rules-doctor` completes, perform a read-only orchestrator-specific audit across:

- `SKILL.md`;
- `README.md`;
- `references/orch-workflow.md`;
- `references/orch-directives/*.md`;
- `evals/evals.json`;
- helper commands in `scripts/orch.py`.

Do not inspect `.work-bundle/knowledge/`. Do not inspect unrelated project files unless the user explicitly expands the diagnosis scope.

## Consistency Checks

Verify:

1. every directive listed in `SKILL.md` has a matching file under `references/orch-directives/`;
2. every directive file has front matter with `name` and `description`;
3. directive front matter `name` matches the directive filename;
4. README, workflow reference, and evals describe the same directive set;
5. helper commands mentioned by directives exist or the directive clearly states the fallback behavior;
6. no directive instructs agents to write outside `.work-bundle/orchestration/` except source/test changes allowed by `execute-plan`;
7. no directive instructs agents to read `.work-bundle/knowledge/` directly when knowledge must go through `keep-summarizing`.
8. every knowledge-using directive has a retrieval policy mapping or an explicit no-retrieval rule;
9. `keep-summarizing` `what-is-helpful` documents gateway mode, `ks.py query`, and `authority | candidate | background | blocked` retrieval roles;
10. keep-summarizing active docs do not advertise legacy note paths or `archived` note status;
11. orchestrator evals that require v3 role labels are backed by directive documentation.

## Workflow Integrity Checks

Verify:

- `create-specification`, `create-implementation-plan`, `create-handoff`, `execute-plan`, `review-plan`, and `doctor` keep distinct responsibilities;
- artifact creation modes do not execute implementation work;
- `execute-plan` checks sub-agent support before delegation;
- `execute-plan` preserves the single-agent fallback and does not fail only because sub-agents are unavailable;
- `execute-plan` does not archive specs, plans, or handoffs;
- `review-plan` is the only directive that archives completed specification, plan, and handoff artifacts;
- `review-plan` creates a repair specification instead of fixing source files when review fails;
- `doctor` stays read-only and reports repair instructions instead of applying them.

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

Confirm `dev-rules-doctor` was used first, diagnostics stayed read-only, directive coverage was checked, directive front matter was checked, workflow responsibilities remained distinct, required fallback paths were present, archival remained isolated to `review-plan`, and no files were changed.
