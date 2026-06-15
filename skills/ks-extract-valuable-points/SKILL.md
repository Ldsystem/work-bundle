---
name: ks-extract-valuable-points
description: 'Extract durable candidate points from mixed source material before persistence.'
---

# ks-extract-valuable-points

## Scope

Extract durable candidate points from mixed source material before persistence.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Extract durable, reusable engineering insights from a conversation or implementation session, break them down by leaf perspectives, then hand off to `ks-write-knowledge`.

## Trigger phrases

- extract durable points
- what should we save from this session
- summarize what we learned
- valuable takeaways
- map extracted points to perspectives
- break extracted points into note targets

## Use when

Reviewing chat, implementation notes, or reviews for knowledge worth persisting.

## Do not use when

The user only wants to find existing knowledge (`ks-what-is-helpful`) or already gave explicit write instructions (`ks-write-knowledge`).

## Required inputs

- Source material (conversation, PR, design excerpt).
- Optional: project slug and scope.
- `references/assets/keep-summarizing/perspectives.md` for granularity and leaf perspective mapping.

## Workflow

1. Apply the structural-value test from `workflow.md` and `ks-structural-value`.
2. Read `references/assets/keep-summarizing/perspectives.md` before proposing targets.
3. Separate durable from temporary material.
4. Split durable findings into atomic units: one durable question per note candidate.
5. Assign each point to the most specific leaf perspective path.
6. For each point, propose target path and update-existing vs create-new.
7. Extract domain semantics from implementation/interface-shaped material into domain/workflow/data targets.
8. Mark duplicates as `duplicate-covered` or propose canonical note plus linked stub.
9. Decompose context-pack material into atomic notes; do not preserve packs as durable units unless explicitly requested.
10. Use separate `open-questions/<lifecycle-stage>/<perspective>` targets for open questions.
11. Persist approved durable points before ending when the user asked for extraction.
12. Stop with `Waiting for your direction` when required direction is missing.
13. If blocking questions cannot be asked mid-work, persist safe points as `draft`, rebuild indexes, then ask remaining questions.
14. Redirect prepared breakdown to `ks-write-knowledge` and rebuild indexes.

## Strict Rules

- Do not output a generic summary as durable knowledge candidates.
- Do not preserve raw conversation order as note structure.
- Do not create a candidate without leaf perspective and structural-value reason.
- Do not create full duplicate notes across perspectives.
- Do not leave domain rules only in implementation/interface candidates.
- Do not treat context packs as canonical durable notes.
- Do not include temporary bugs, credentials, tokens, or personal data.
- Do not persist agent-generated uncertainty as open questions without user confirmation.
- Do not end with only proposed targets when safe persistence is possible.

## Return

- durable points; non-durable points to ignore; possible structural updates
- perspective breakdown per point (leaf path, reason, target path, update/create)
- suggested titles; confidence; source evidence
- written or updated note paths when persistence was safe
- index rebuild status; blocking questions when required

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-structural-value`: `rules/keep-summarizing/ks-structural-value.md`
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

## Boundary

Write only under `.work-bundle/knowledge/` allowed paths; redirect orchestration artifacts to orch-* skills.
