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
- `python3 bin/work-bundle-skill validate` output when available on macOS/Linux, or the equivalent `py -3.13`/resolved `python` command on Windows.

Do not inspect `.work-bundle/knowledge/` note bodies unless the user explicitly expands diagnosis scope. Do not inspect unrelated project files unless the user explicitly expands the diagnosis scope.

## Consistency Checks

Verify:

1. every ks skill in the workflow reference has a matching `skills/ks-*/SKILL.md` file;
2. front matter `name` matches the skill directory name;
3. Runtime Rules paths exist on disk;
4. central `AGENTS.md` discovery/reuse and accepted-worker obligations are referenced without a local mandatory rereading algorithm;
5. workflow body rule references are covered by Runtime Rules (OQ-001–003 pattern);
6. Boundary sections use pointer-only format (OQ-004);
7. no duplicated shared Must/Must Not prose in skill bodies for rule-owned policy;
8. activated skill links under the shared agent skill root resolve to this repo.

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

Confirm diagnostics stayed read-only, ks skill coverage and front matter were checked, procedural rule paths resolve, central discovery/reuse pointers replace local mandatory rereading, Boundary sections use pointer-only format, duplicated shared policy is absent, install symlinks resolve when applicable, and no files changed. Mechanical findings do not establish semantic trigger coverage.

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`

Central `AGENTS.md` owns indexed rule discovery and exact-context body reuse. Consume carried task-local obligations in an accepted worker packet; these Runtime Rules are procedural pointers, not a separate loading algorithm.

## Read-Only Constraints (skill-owned)

Diagnose keep-summarizing skill and rule boundary integrity without mutating project files, durable knowledge, indexes, or configuration. Doctor collects independent findings and reports concrete repair actions.

### Must

- Perform a read-only audit across ks skill files, keep-summarizing rules, workflow reference, boundary tests, and skill validation output when available.
- Verify skill coverage, front matter consistency, procedural rule path existence, central discovery/reuse pointers, workflow citation alignment, pointer-only Boundary format, absence of duplicate loading/shared-policy algorithms, and install symlink resolution when applicable.
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
