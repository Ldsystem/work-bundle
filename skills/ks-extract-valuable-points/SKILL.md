---
name: ks-extract-valuable-points
description: 'Extract reusable knowledge candidates from a mixed conversation, implementation session, or review before persistence. Excludes existing-note lookup and settled explicit writes.'
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

Run extraction per **Extraction Constraints (skill-owned)**.

Apply loaded Runtime Rules:

- Structural-value gate: follow `ks-structural-value`
- Perspective fit, leaf path, granularity, and domain routing: follow `ks-perspective-routing` and perspective mapping from `references/assets/keep-summarizing/perspectives.md`
- Sensitivity exclusions: follow `ks-sensitivity-filter`
- Persistence gates and off-switches: follow `ks-persistence-gate` and `ks-off-switches`
- Context-pack handling: follow `ks-context-pack-policy` and workflow decomposition steps in **Extraction Constraints (skill-owned)**
- Open-question confirmation: follow `ks-open-question-policy`

## Strict Rules

Apply loaded Runtime Rules per **Workflow** pointer list.

### Must Not (skill-owned)

- Do not output a generic summary as durable knowledge candidates.
- Do not preserve raw conversation order as note structure.

## Return

Deliver the candidate table and status fields defined in **Extraction Constraints (skill-owned)**.

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-structural-value`: `rules/keep-summarizing/ks-structural-value.md`
- `ks-perspective-routing`: `rules/keep-summarizing/ks-perspective-routing.md`
- `ks-context-pack-policy`: `rules/keep-summarizing/ks-context-pack-policy.md`
- `ks-open-question-policy`: `rules/keep-summarizing/ks-open-question-policy.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`
- `ks-off-switches`: `rules/keep-summarizing/ks-off-switches.md`

Central `AGENTS.md` owns indexed rule discovery and exact-context body reuse. Consume carried task-local obligations in an accepted worker packet; these Runtime Rules are procedural pointers, not a separate loading algorithm.

## Extraction Constraints (skill-owned)

### Session extraction ordering

1. Apply the structural-value test from `workflow.md` and `ks-structural-value`.
2. Read `references/assets/keep-summarizing/perspectives.md` before proposing targets.
3. Separate durable from temporary material.
4. Split durable findings into atomic units: one durable question per note candidate.
5. Assign each point to the most specific leaf perspective path.
6. For each point, propose target path and update-existing vs create-new.
7. Extract domain semantics from implementation/interface-shaped material into domain/workflow/data targets.
8. Mark duplicates as `duplicate-covered` or propose canonical note plus linked stub after duplicate/conflict discovery through approved neutral query surfaces, not broad JSONL browsing.
9. Decompose context-pack material into atomic notes; do not preserve packs as durable units unless explicitly requested.
10. Use separate `open-questions/<lifecycle-stage>/<perspective>` targets for open questions.
11. Persist approved durable points before ending when the user asked for extraction.
12. Redirect accepted record effects to `ks-write-knowledge` or `ks-track-open-questions`; consume their transaction outcomes, including vector-inclusive derived index status, instead of performing duplicate index work.

### Candidate table shape

Each candidate row includes:

- durable point summary
- leaf perspective path and mapping reason
- target path and update-existing vs create-new
- suggested title, confidence, and source evidence
- duplicate status (`duplicate-covered` or canonical note plus linked stub)

Also return:

- durable points; non-durable points to ignore; possible structural updates
- perspective breakdown per point (leaf path, reason, target path, update/create)
- suggested titles; confidence; source evidence
- written or updated note paths when persistence was safe
- index rebuild status; blocking questions when required

### Safe-draft mid-work persistence flow

- Stop with `Waiting for your direction` when required direction is missing.
- When blocking questions cannot be asked mid-work, send only authorized safe draft effects through the corresponding record writer, consume its projection outcome, then ask remaining questions.
- Do not end with only proposed targets when safe persistence is possible.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
