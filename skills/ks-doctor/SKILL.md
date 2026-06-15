---
name: ks-doctor
description: 'Run read-only keep-summarizing skill and rule boundary diagnostics.'
---

# ks-doctor

## Scope

Run read-only keep-summarizing skill and rule boundary diagnostics.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

This skill is read-only and must not repair, rewrite, delete, archive, or generate keep-summarizing artifacts.

## Keep-Summarizing Audit Scope

Perform a read-only keep-summarizing boundary audit across:

- all `skills/ks-*/SKILL.md` (excluding self when needed for circular checks);
- all `rules/keep-summarizing/*.md`;
- `references/assets/keep-summarizing/workflow.md`;
- `tests/test_keep_summarizing_skill_rule_boundary.py`;
- `bin/work-bundle-skill validate` output when available.

Do not inspect `.work-bundle/knowledge/` note bodies unless the user explicitly expands diagnosis scope. Do not inspect unrelated project files unless the user explicitly expands the diagnosis scope.

## Consistency Checks

Verify:

1. every ks skill in the workflow reference has a matching `skills/ks-*/SKILL.md` file;
2. front matter `name` matches the skill directory name;
3. Runtime Rules paths exist on disk;
4. `## Rule Loading (mandatory)` follows `## Runtime Rules` on every citing skill;
5. workflow body rule references are covered by Runtime Rules (OQ-001–003 pattern);
6. Boundary sections use pointer-only format (OQ-004);
7. no duplicated shared Must/Must Not prose in skill bodies for rule-owned policy;
8. `bin/install-work-bundle-skills` symlinks resolve to this repo.

## Output

```text
Doctor result: passed|issues-found|blocked
Keep-summarizing consistency:
- <passed or issue summary>
Recommended repairs:
- <concrete repair action or none>
Files changed: none
```

## Validation

Confirm diagnostics stayed read-only, ks skill coverage was checked, skill front matter was checked, Runtime Rules paths were verified, Rule Loading sections were present, Boundary sections used pointer-only format, duplicated shared prose was absent, install symlinks resolved, and no files were changed.

## Runtime Rules

- `ks-doctor-readonly`: `rules/keep-summarizing/ks-doctor-readonly.md`

## Rule Loading (mandatory)

Before substantive doctor work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive keep-summarizing doctor work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or directive summaries as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress doctor task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Read-Only Constraints (skill-owned)

Diagnose keep-summarizing skill and rule boundary integrity without mutating project files, durable knowledge, indexes, or configuration. Doctor collects independent findings and reports concrete repair actions.

### Must

- Perform a read-only audit across ks skill files, keep-summarizing rules, workflow reference, boundary tests, and skill validation output when available.
- Verify skill coverage, front matter consistency, Runtime Rules path existence, Rule Loading presence, workflow-to-Runtime-Rules citation alignment, pointer-only Boundary format, absence of duplicated rule-owned prose, and install symlink resolution.
- Report findings as concrete repair actions with cited conflicting artifacts when issues are found.
- Emit doctor output with `Files changed: none`.

### Must Not

- Edit, repair, rewrite, delete, archive, or generate keep-summarizing artifacts during doctor.
- Mutate source files, project files, durable knowledge, indexes, rules, skills, or configuration as part of diagnosis.
- Inspect `.work-bundle/knowledge/` note bodies or unrelated project files unless the user explicitly expands diagnosis scope.
- Apply fixes directly instead of reporting recommended repairs.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
