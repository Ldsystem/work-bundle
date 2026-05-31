# write-knowledge

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
- User only asked what exists (`what-is-helpful`).
- Weak approval only (see confirmation strength in `SKILL.md`).

## Required inputs

- Target perspective path and title.
- Note content or source to extract from.
- Lifecycle status when not `current`.
- `references/ks-perspectives.md` for leaf perspective validation.

## Workflow

1. Run `guard-scope` checks. Stop on any failure.
2. Read `references/ks-workflow.md` and apply the Mandatory Persistence Gate.
3. Read `references/ks-perspectives.md` for leaf path.
4. Validate the target path is a specific leaf perspective path, not a broad container.
5. Validate granularity: one durable question per note.
6. Check existing registry/index entries and note bodies for duplicates or conflicts.
7. Ask before overwriting, replacing, or deprecating a conflicting `current` note.
8. If the point duplicates an existing durable fact in another perspective, choose or ask for one canonical note; use a short linked stub in the secondary perspective only when cross-perspective discovery is useful.
9. If the source is implementation- or interface-shaped but contains stable domain semantics, extract the domain rule into a domain, workflow, data, validation, or source-of-truth note before updating the implementation/interface note.
10. Write only after the target path, lifecycle status, and content boundaries are explicit.
11. Rebuild indexes after changes (`maintain-indexes`).

## Rules

- do not write when `draft only`, `pause keep-summarizing`, or `do not summarize this` is active
- do not create files outside `notes/<lifecycle-stage>/<leaf-perspective>/`, `open-questions/<lifecycle-stage>/<leaf-perspective>/`, or `context-packs/`
- preserve required front matter
- keep one note focused on one concept
- prefer updating existing notes over creating duplicates
- do not create full duplicate notes across perspectives; use one canonical note plus a short linked stub when needed
- add relative links to related notes
- require a leaf perspective path justified by `references/ks-perspectives.md`
- cite source paths or note IDs when source material exists
- exclude raw chat logs, temporary command output, credentials, tokens, personal data, and one-off debugging details
- do not let implementation or interface notes become the only source for stable domain rules
- do not mark inferred or weakly approved material as `current`
- leave uncertain facts as non-persisted open questions in the response
- write open questions to notes only when the user provided them or confirmed they are valuable future work

## Stop Conditions

Return `Waiting for your direction` instead of writing when:

- project resolution fails
- target perspective is broad or missing
- lifecycle status is unclear
- source material contradicts an existing `current` note
- source material duplicates an existing `current` note and no canonical note is selected
- implementation-shaped material contains domain rules but no target domain/workflow/data note is selected
- the user gave only weak approval
- the request mixes durable knowledge with reader-facing output, handoff, plan, or specification work

## Return

- paths written or updated
- leaf perspective path and mapping reason
- lifecycle status
- index rebuild status
- any non-persisted open questions
