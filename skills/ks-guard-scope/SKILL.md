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

Run preflight checks per **Preflight Constraints (skill-owned)**.

Apply loaded Runtime Rules:

- Knowledge root and path scope: follow `ks-knowledge-boundary`
- Sensitivity and metadata: follow `ks-sensitivity-filter`
- Persistence gates: follow `ks-persistence-gate`
- Off-switches: follow `ks-off-switches`
- Git allowlist: follow `ks-git-authority`

Reader-facing documents: redirect to `orch-create-document` and inherit source sensitivity there.

## Return

- pass or fail per check
- blocking issues and required user action

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`
- `ks-off-switches`: `rules/keep-summarizing/ks-off-switches.md`
- `ks-git-authority`: `rules/keep-summarizing/ks-git-authority.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Preflight Constraints (skill-owned)

### Registry resolution

When registry data is used:

- Resolve project data from `~/.work-bundle/registry/projects.yaml`, `KS_PROJECT_REGISTRY`, or `--registry-file`.
- Treat registry data as local runtime state, not durable knowledge.

### Embedding-export exclusions

- Exclude blocked statuses and sensitivities from embedding export per loaded `ks-sensitivity-filter` and `ks-persistence-gate` rules.

### Per-check pass/fail matrix

| Check | Pass | Fail |
| --- | --- | --- |
| Knowledge root | Selected project resolves to `.work-bundle/knowledge/` or an explicitly selected external legacy root for migration/read-only intake | Selected root is invalid or unresolved |
| Target path scope | Target path is inside the selected knowledge repo | Target is under `.work-bundle/orchestration/` or outside the selected knowledge repo |
| Note path | Target is under `notes/<lifecycle-stage>/<leaf-perspective>/` | Wrong path, broad perspective, or missing perspective |
| Open-question path | Target is under `open-questions/<lifecycle-stage>/<leaf-perspective>/` | Wrong path, broad perspective, or missing perspective |
| Knowledge root write | — | Write would create Markdown at the knowledge root |
| Git scope | Git command is allowlisted per `ks-git-authority` in the selected knowledge repo | Git requested outside the selected knowledge repo |
| Note metadata | Note has `visibility` and `sensitivity` per `ks-sensitivity-filter` | Missing or invalid metadata |
| Sensitivity/content | Passes `ks-sensitivity-filter` | Excluded material would be persisted |
| Persistence gates | Passes `ks-persistence-gate` | Gate blocks the operation |
| Off-switches | Passes `ks-off-switches` | Switch blocks the operation |
| Embedding export | Blocked statuses and sensitivities excluded | Blocked content would be exported |
| Reader-facing docs | Redirect to `orch-create-document` | — |

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
