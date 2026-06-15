---
name: ks-breakdown-design
description: 'Decompose design files into perspective-aligned durable knowledge notes.'
---

# ks-breakdown-design

## Scope

Decompose design files into perspective-aligned durable knowledge notes.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Break down a design file into desired parts and target knowledge locations while preserving every meaningful source point.

This is an agent reasoning workflow, not a mechanical parser. User-provided design files may be brainstorms, incomplete outlines, mixed conversations, or poorly structured drafts. Understand and restructure content before any persistence script is used.

## Trigger phrases

- break down this design
- split design into knowledge notes
- design file to notes

## Use when

The user has a design file (messy or structured) to map into durable knowledge notes.

## Do not use when

The user only wants to find existing knowledge (`ks-what-is-helpful`) or generate a reader-facing doc (`orch-create-document`).

## Key parameters

- `input_file`
- `desired_parts`
- `output_language`
- `target_project`
- `target_mode`: plan-only, draft-notes, or apply-updates
- `granularity`: chapter, section, or atomic-note
- `preserve_original_order`
- `include_traceability`
- `perspective_reference`: always `references/assets/keep-summarizing/perspectives.md`

## Workflow

1. Read the full design file before proposing a breakdown.
2. Read `references/assets/keep-summarizing/perspectives.md` as the mapping contract.
3. Identify design intent even if headings are weak, duplicated, or missing.
4. Separate durable conclusions from brainstorming, rejected options, and non-persisted open questions.
5. Infer themes and group by requested `desired_parts`.
6. Compare with existing notes before proposing new files; prefer updates over duplicates.

Run breakdown mapping, coverage, and persistence per **Coverage Constraints (skill-owned)**.

Apply loaded Runtime Rules:

- Perspective fit, leaf path, granularity, and domain routing: follow `ks-perspective-routing`
- Structural-value gate: follow `ks-structural-value`
- Persistence gates: follow `ks-persistence-gate`
- Sensitivity exclusions: follow `ks-sensitivity-filter`
- Index maintenance: follow `ks-index-maintenance`
- Off-switches: follow `ks-off-switches`

Use scripts only after the breakdown plan exists and persistence is approved.

## Strict Coverage Rules

Apply loaded Runtime Rules per **Workflow** pointer list.

### Must Not (skill-owned)

- Do not skip meaningful uncertain points; map to `draft` candidates.
- Do not copy the design file as a standalone knowledge file.

## Return

- inferred design themes; breakdown table; target files or proposed note IDs
- target leaf perspective and granularity reason per durable point
- coverage report (mandatory); non-persisted open questions; conflicts
- persistence plan; suggested script commands when applying
- waiting status and next actions when not applying immediately
- written or updated note paths and index status when persistence was safe

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-structural-value`: `rules/keep-summarizing/ks-structural-value.md`
- `ks-perspective-routing`: `rules/keep-summarizing/ks-perspective-routing.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`
- `ks-index-maintenance`: `rules/keep-summarizing/ks-index-maintenance.md`
- `ks-off-switches`: `rules/keep-summarizing/ks-off-switches.md`

## Rule Loading (mandatory)

Before substantive keep-summarizing work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive knowledge work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or summarized rule text as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Coverage Constraints (skill-owned)

### Breakdown mapping

- Preserve every meaningful source point as an atomic note or update candidate; unsettled points become `draft` candidates.
- Map each point to the most specific leaf perspective path per loaded `ks-perspective-routing`.
- Enforce granularity: one source point or durable question per proposed note.
- Preserve traceability to source file, heading path, point order, and excerpt.

### Coverage report and breakdown map

- Return a coverage report mapping every source point to a note or update candidate.
- Add a breakdown map linking source sections to note IDs for semantic recovery.
- Every coverage row includes: source heading/path, point order, target leaf perspective, target candidate, disposition.
- Dispositions: `new-note`, `update-existing`, `duplicate-covered`, `draft-candidate`, or `open-question-candidate`.
- If any meaningful point cannot be mapped, stop with `Waiting for your direction`.

### target_mode handling

- Persist approved durable points before ending unless `target_mode` is `plan-only` or `draft only`.
- Return a plan first only when `target_mode` is `plan-only`, confidence is low, or a safety gate blocks persistence.

### Persistence handoff

- When applying updates: use `ks-write-knowledge` for notes and `ks-track-open-questions` for confirmed open questions; then `ks-maintain-indexes`.
- If blocking questions cannot be asked mid-work, persist safe points, write uncertain points as `draft`, rebuild indexes, then ask remaining questions.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
