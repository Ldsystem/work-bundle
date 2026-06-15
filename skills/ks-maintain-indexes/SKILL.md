---
name: ks-maintain-indexes
description: 'Rebuild derived keep-summarizing indexes after durable knowledge changes.'
---

# ks-maintain-indexes

## Scope

Rebuild derived keep-summarizing indexes after durable knowledge changes.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Maintain generated index files from curated Markdown.

## Trigger phrases

- rebuild indexes
- refresh document registry
- reindex

## Use when

After durable note or open-question changes.

## Do not use when

Indexes are already current and no Markdown changed.

## Required inputs

- Project slug.
- Optional: project root path.

## Workflow

1. Run `scripts/ks.py index --project <slug>` after note changes.
2. Run `scripts/ks.py index-open-questions --project <slug>` after open-question changes.
3. Report duplicates, broken links, and missing metadata.

Index completion and maintenance policy: follow `ks-index-maintenance`.

## Return

- commands run
- issues found (duplicates, broken links, missing metadata)

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-index-maintenance`: `rules/keep-summarizing/ks-index-maintenance.md`
- `ks-git-authority`: `rules/keep-summarizing/ks-git-authority.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
