# breakdown-design

## Intent

Break down a design file into desired parts and target knowledge locations while preserving every meaningful source point.

This directive is an agent reasoning workflow, not a mechanical parser. User-provided design files may be brainstorms, incomplete outlines, mixed conversations, or poorly structured drafts. The agent must understand and restructure the content before any persistence script is used.

## Trigger phrases

- break down this design
- split design into knowledge notes
- design file to notes

## Use when

The user has a design file (messy or structured) to map into durable knowledge notes.

## Do not use when

The user only wants to find existing knowledge (`what-is-helpful`) or generate a reader-facing doc (use `orch-create-document`).

## Key parameters

- `input_file`
- `desired_parts`
- `output_language`
- `target_project`
- `target_mode`: plan-only, draft-notes, or apply-updates
- `granularity`: chapter, section, or atomic-note
- `preserve_original_order`
- `include_traceability`
- `perspective_reference`: always `references/ks-perspectives.md`

## Workflow

1. Read the full design file before proposing a breakdown.
2. Read `references/ks-perspectives.md` and use it as the mapping contract.
3. Identify the user's actual design intent, even if the file headings are weak, duplicated, or missing.
4. Separate durable conclusions from brainstorming, temporary exploration, rejected options, and non-persisted open questions.
5. Infer themes and group them by the requested `desired_parts`.
6. Preserve every meaningful source point as an atomic note or update candidate; unsettled points should become `draft` candidates, not discarded leftovers.
7. Map each point to the most specific leaf perspective path from `references/ks-perspectives.md`.
8. Enforce granularity: one source point or one durable question per proposed note, reject container-level target paths.
9. Preserve traceability to source file, source heading path, source point order, and concise source excerpt.
10. Compare with existing notes before proposing new files.
11. Prefer updating existing notes over creating duplicates.
12. Return a coverage report showing every source point mapped to a note or update candidate.
13. Add a breakdown map, such as a context pack or index-style artifact, linking source sections and point order to note IDs for semantic recovery.
14. Persist approved durable points before ending the current conversation unless `target_mode` is explicitly `plan-only` or `draft only`.
15. Return a plan first only when `target_mode` is `plan-only`, confidence is low, or a safety gate blocks persistence.
16. If returning a plan first, explicitly say `Waiting for your direction` and ask the minimum questions needed to persist safely.
17. Use scripts only after the agent has produced the breakdown plan and needs to persist notes, rebuild indexes, or run scoped Git.

## Strict Coverage Rules

- Do not skip a meaningful source point because it is uncertain; map it to a `draft` candidate.
- Do not copy the design file as a standalone knowledge file.
- Do not preserve source document structure as the note tree; use leaf perspectives.
- Do not use broad paths such as `architecture`, `data-flow`, or `decisions`.
- Every coverage row must include source heading/path, point order, target leaf perspective, target note/update candidate, and disposition.
- Dispositions are limited to `new-note`, `update-existing`, `duplicate-covered`, `draft-candidate`, or `open-question-candidate`.
- If any meaningful point cannot be mapped, stop and return `Waiting for your direction`.
- If applying updates, run `write-knowledge` for notes and `track-open-questions` for confirmed open questions; then run `maintain-indexes`.
- Do not end the conversation after only listing note candidates when persistence is safe and the user asked to break down the file into knowledge.
- If the agent cannot ask blocking questions mid-work, persist safe points, write uncertain valuable points as `draft`, rebuild indexes, then ask remaining questions at the end.

## Return

- inferred design themes
- breakdown table
- target files or proposed note IDs
- target leaf perspective path and granularity reason for each durable point
- durable points per part
- coverage report for all meaningful source points
- non-persisted open questions
- conflicts with existing notes
- persistence plan
- suggested script commands only for applying the accepted breakdown
- waiting status and next action choices when not applying immediately

The coverage report is mandatory. If the response has no coverage report, the directive is incomplete. If persistence was safe, written or updated note paths and index rebuild status are also mandatory.

## Persistence rule

- Return agent-generated open questions to the user by default.
- Persist open questions only when the user provides them as future problems or confirms they should be tracked.
- If persisted, create or update a standalone note under `open-questions/`.
