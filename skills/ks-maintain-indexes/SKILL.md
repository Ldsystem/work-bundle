---
name: ks-maintain-indexes
description: 'Rebuild derived knowledge indexes after canonical changes or on an explicit stale, missing, or deleted projection recovery request. A successful mutation rebuild needs no duplicate run.'
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

After durable changes with unresolved projection recovery, or when explicitly asked to regenerate stale, missing, or deleted indexes.

## Do not use when

The mutation command already reported current/rebuilt projections and no regeneration was requested.

## Required inputs

- Project slug.
- Optional: project root path.

## Workflow

1. Inspect the mutation outcome first. `projection_status: rebuilt` satisfies that operation's rebuild; do not blindly rerun it. `canonical_status: replaced` with `projection_status: stale` leaves valid Markdown authoritative and supplies an existing `rebuild_command`.
2. Run that returned command for stale recovery, or `scripts/ks.py index --project <slug>` / `scripts/ks.py index-open-questions --project <slug>` for the explicitly requested note/open-question projection regeneration.
3. Report derived index status for document registry, chunk registry, SQLite FTS, vector index artifacts, embedding manifest or chunk hashes, and open-question registry when relevant.
4. Report duplicates, broken links, missing metadata, vector unavailability, and any other mechanical rebuild issue before claiming completion.

Index completion and maintenance policy: follow `ks-index-maintenance`.

## Return

- commands run
- index status, including vector index status (`rebuilt`, `unavailable`, `skipped`, or `failed`)
- issues found (duplicates, broken links, missing metadata, vector unavailability, failed rebuilds)

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-index-maintenance`: `rules/keep-summarizing/ks-index-maintenance.md`
- `ks-git-authority`: `rules/keep-summarizing/ks-git-authority.md`

Central `AGENTS.md` owns indexed rule discovery and exact-context body reuse. Consume carried task-local obligations in an accepted worker packet; these Runtime Rules are procedural pointers, not a separate loading algorithm.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
