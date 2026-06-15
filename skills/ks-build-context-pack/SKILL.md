---
name: ks-build-context-pack
description: 'Build temporary agent context packs from canonical durable knowledge.'
---

# ks-build-context-pack

## Scope

Build temporary agent context packs from canonical durable knowledge.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Build compact context packs for future agents under `context-packs/`.

## Trigger phrases

- build context pack
- update current context
- agent context for this project

## Use when

The user wants temporary agent scaffolding derived from durable notes.

## Do not use when

The user only wants a one-off reading list (`ks-what-is-helpful`) or a handoff request for `orch-create-handoff`.

## Required inputs

- Project slug.
- Current goal and stable assumptions.
- Optional: scope of perspectives to include.

## Workflow

1. Gather current goal, assumptions, flows, architecture, conventions, decisions, non-goals, and risks from curated notes.
2. Build or refresh the context pack per **Context Pack Constraints (skill-owned)**.

Context-pack policy: follow `ks-context-pack-policy`.

## Return

- path to the context pack
- what was included and excluded
- whether indexes need rebuild

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-structural-value`: `rules/keep-summarizing/ks-structural-value.md`
- `ks-context-pack-policy`: `rules/keep-summarizing/ks-context-pack-policy.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Context Pack Constraints (skill-owned)

### Pack assembly

- Treat atomic perspective notes as authoritative. Do not make the context pack the only home for any durable rule.
- Write or update `context-packs/current.md` (or named pack).
- Do not duplicate large note bodies into a context pack; summarize and link to canonical notes.
- If the pack contains facts not present in canonical notes, extract those facts before treating them as durable.
- Avoid raw logs, excessive history, temporary debugging, and stale assumptions.

### Expiry metadata

- Add or update expiry metadata or a visible review note when the pack should be refreshed.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
