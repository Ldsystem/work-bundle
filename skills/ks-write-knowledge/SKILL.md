---
name: ks-write-knowledge
description: 'Write or update atomic durable knowledge notes after all persistence gates pass.'
---

# ks-write-knowledge

## Scope

Write or update atomic durable knowledge notes after all persistence gates pass.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Write or update curated Markdown notes under `notes/<lifecycle-stage>/<leaf-perspective>/`.

## Trigger phrases

- persist this
- save as current
- write a note
- update the knowledge base

## Use when

The user explicitly requests persistence or gave a strong persist signal.

## Do not use when

- Draft only (`draft only` off-switch).
- User only asked what exists (`ks-what-is-helpful`).
- Weak approval only (see confirmation strength in Runtime Rules).

## Required inputs

- Target perspective path and title.
- Note content or source to extract from.
- Lifecycle status when not `current`.
- `references/assets/keep-summarizing/perspectives.md` for leaf perspective validation.

## Workflow

1. Run `ks-guard-scope` checks. Stop on any failure.
2. Apply the Mandatory Persistence Gate from `workflow.md` and `ks-persistence-gate`.
3. Read `references/assets/keep-summarizing/perspectives.md` for leaf path validation.
4. Validate target is a specific leaf perspective, not a broad container.
5. Validate granularity: one durable question per note.
6. Check duplicates or conflicts through the approved query surface using neutral artifact, feature, functionality, component, file, API, schema, workflow, or explicit-name anchors. Do not browse JSONL indexes as the exploration path; JSONL remains a derived compatibility index.
7. Ask before overwriting, replacing, or deprecating a conflicting `current` note.
8. If the point duplicates an existing durable fact, choose or ask for one canonical note; use a short linked stub in secondary perspectives when useful.
9. If source is implementation- or interface-shaped but contains stable domain semantics, extract into domain/workflow/data/validation/source-of-truth notes first.
10. Write only after target path, lifecycle status, and content boundaries are explicit.
11. Rebuild indexes via `ks-maintain-indexes`; completion requires vector-inclusive derived index status when relevant.

Apply loaded Runtime Rules:

- Off-switches: follow `ks-off-switches`
- Knowledge root and path scope: follow `ks-knowledge-boundary`
- Sensitivity exclusions: follow `ks-sensitivity-filter`
- Open-question confirmation: follow `ks-persistence-gate` and `ks-note-state-authority`
- Index completion: follow `ks-index-maintenance`

Operational rules (skill-owned):

- preserve required front matter; one concept per note
- prefer updating existing notes over duplicates
- cite source paths when material exists

## Stop Conditions

Return `Waiting for your direction` instead of writing when:

- project resolution fails
- target perspective is broad or missing
- lifecycle status is unclear
- source contradicts or duplicates a `current` note without resolution
- implementation-shaped material contains domain rules but no semantic target is selected

Weak approval and mixed-artifact stop conditions: follow **Write Constraints (skill-owned)**.

## Return

- paths written or updated
- leaf perspective path and mapping reason
- lifecycle status
- index rebuild status
- any non-persisted open questions

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-structural-value`: `rules/keep-summarizing/ks-structural-value.md`
- `ks-perspective-routing`: `rules/keep-summarizing/ks-perspective-routing.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`
- `ks-index-maintenance`: `rules/keep-summarizing/ks-index-maintenance.md`
- `ks-git-authority`: `rules/keep-summarizing/ks-git-authority.md`
- `ks-note-state-authority`: `rules/keep-summarizing/ks-note-state-authority.md`
- `ks-off-switches`: `rules/keep-summarizing/ks-off-switches.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Write Constraints (skill-owned)

Return `Waiting for your direction` instead of writing when:

- the user gave only weak approval
- the request mixes durable knowledge with reader-facing output, handoff, plan, or specification work

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
