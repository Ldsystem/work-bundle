---
name: ks-write-knowledge
description: 'Create or update atomic durable notes when persistence is explicitly authorized and content, ownership, and lifecycle intent are settled. Excludes retrieval and draft-only requests.'
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

The user explicitly requests persistence, gave a strong persist signal, or the approved workflow already requires this bounded knowledge follow-up.

## Do not use when

- Draft only (`draft only` off-switch).
- User only asked what exists (`ks-what-is-helpful`).
- Weak approval only, with no existing approved persistence intent (see confirmation strength in Runtime Rules).

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
7. Resolve authority before overwriting, replacing, or deprecating a conflicting `current` note; ask only when that decision is not already explicitly authorized.
8. If the point duplicates an existing durable fact, choose or ask for one canonical note; use a short linked stub in secondary perspectives when useful.
9. If source is implementation- or interface-shaped but contains stable domain semantics, extract into domain/workflow/data/validation/source-of-truth notes first.
10. Decide structural value, relevance, authority, conflict disposition, sensitivity meaning, lifecycle intent, and evidence sufficiency before requesting persistence. Existing explicit persistence or approved workflow follow-up supplies intent within its scope; ask only for unresolved decisions.
11. Prepare the complete one-record `create` or `update` request from the shared workflow: `effect`, `kind: note`, canonical knowledge-relative `path`, `expected_digest`, complete `record` front matter, and exact Markdown `body`. Use `null` digest for an absent create target; otherwise use `sha256:<digest>` of current canonical bytes. An update preserves identity, perspective, and status; a status change belongs to `ks-manage-lifecycle`.
12. Invoke `python3 scripts/ks.py mutate-knowledge --project <slug> --request-file <request.yaml>`; use `--dry-run` when an effect preview is useful. Do not perform ad hoc canonical file or index mutations.
13. Consume the actual canonical and projection outcomes. A successful rebuild needs no duplicate index run; if `canonical_status: replaced` and `projection_status: stale`, preserve the record and report/regenerate the index using the returned rebuild command.

Apply loaded Runtime Rules:

- Off-switches: follow `ks-off-switches`
- Knowledge root and path scope: follow `ks-knowledge-boundary`
- Sensitivity exclusions: follow `ks-sensitivity-filter`
- Open-question confirmation: follow `ks-open-question-policy`
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
- `ks-open-question-policy`: `rules/keep-summarizing/ks-open-question-policy.md`

Central `AGENTS.md` owns indexed rule discovery and exact-context body reuse. Consume carried task-local obligations in an accepted worker packet; these Runtime Rules are procedural pointers, not a separate loading algorithm.

## Write Constraints (skill-owned)

Return `Waiting for your direction` instead of writing when:

- the user gave only weak approval and no approved workflow supplies persistence intent
- a mixed knowledge/output, handoff, plan, or specification request leaves the persistence scope, content, or intent unsettled; mixed artifact labels alone do not block an already approved bounded workflow follow-up

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).

## Self-check

- [ ] Agent decisions and authorized intent are settled; no internal reasoning is serialized into the request.
- [ ] The request names one exact record, complete content/front matter, effect, path, and current digest.
- [ ] The declared command performed the mutation; no direct canonical edit or manual index patch was used.
- [ ] Canonical replacement and derived projection status are reported separately, without a semantic verdict from command success.
