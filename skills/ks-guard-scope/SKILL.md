---
name: ks-guard-scope
description: 'Enforce knowledge write scope, sensitivity, and safety boundaries.'
---

# ks-guard-scope

## Scope

Enforce knowledge write scope, sensitivity, and safety boundaries.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Enforce project knowledge boundaries, sensitivity metadata, and embedding exclusions.

## Trigger phrases

- check knowledge scope
- sensitivity check
- is this path allowed

## Use when

Before any write, index export, or Git operation in the knowledge repo.

## Workflow

Verify:

- selected project resolves to `.work-bundle/knowledge/` or an explicitly selected external legacy root for migration/read-only intake
- registry data, when used, comes from `~/.work-bundle/registry/projects.yaml`, `KS_PROJECT_REGISTRY`, or `--registry-file`, and is treated as local runtime state
- target path is inside the selected knowledge repo
- Git command is allowlisted (see `ks-git-authority`)
- note has `visibility` and `sensitivity` (see `ks-sensitivity-filter`)
- embedding export excludes blocked statuses and sensitivities
- reader-facing documents are redirected to `orch-create-document` and inherit source sensitivity there

Fail if:

- the target path is under `.work-bundle/orchestration/`
- the target path is outside the selected knowledge repo
- the note target is not under `notes/<lifecycle-stage>/<leaf-perspective>/`
- the open-question target is not under `open-questions/<lifecycle-stage>/<leaf-perspective>/`
- the target perspective is broad or missing
- the write would create Markdown at the knowledge root
- the operation would copy raw source files, raw design files, transcripts, logs, credentials, tokens, or personal data into knowledge
- Git is requested outside the selected knowledge repo
- persistence gates or off-switches block the operation (see Runtime Rules)

## Return

- pass or fail per check
- blocking issues and required user action

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`
- `ks-off-switches`: `rules/keep-summarizing/ks-off-switches.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Write only under `.work-bundle/knowledge/` allowed paths; redirect orchestration artifacts to orch-* skills.
