---
name: ks-resolve-conflicts
description: 'Resolve identified contradictory or duplicate durable notes and choose canonical ownership before requesting record effects. Excludes straightforward updates with no identified conflict.'
---

# ks-resolve-conflicts

## Scope

Resolve duplicate or conflicting durable knowledge notes with canonical ownership.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Resolve overlap or contradiction between curated notes.

## Trigger phrases

- conflicting notes
- merge these notes
- contradictory knowledge

## Use when

Two or more notes disagree or duplicate the same concept.

## Do not use when

There is no identified conflict; use `ks-write-knowledge` for straightforward updates.

## Required inputs

- Conflicting note paths or IDs.
- User preference when known.

## Workflow

1. Compare content and front matter.
2. Complete the shared workflow's agent decision preconditions and choose canonical ownership/resolution per **Conflict Resolution Constraints (skill-owned)**; the script does not decide which note is better.
3. After resolving authority and intent, author exact replacement content and declared links. If a replacement note is needed, create/update it through `ks-write-knowledge` first; then use `ks-manage-lifecycle` for each separately authorized supersession/deprecation. Each request mutates one record and references existing replacements, rather than treating a merge as a multi-record transaction.
4. Invoke `python3 scripts/ks.py mutate-knowledge --project <slug> --request-file <request.yaml>` for the declared effect using the shared complete `effect/kind/path/expected_digest/record/body` request. Keep internal conflict reasoning out of it and consume canonical/projection outcomes separately.

## Return

- decision taken or recommended
- affected paths
- whether user confirmation is required

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-perspective-routing`: `rules/keep-summarizing/ks-perspective-routing.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`

Central `AGENTS.md` owns indexed rule discovery and exact-context body reuse. Consume carried task-local obligations in an accepted worker packet; these Runtime Rules are procedural pointers, not a separate loading algorithm.

## Conflict Resolution Constraints (skill-owned)

- Choose one resolution path: `merge`, `replace`, `create-new`, or `ask-user`.
- Do not silently overwrite contradictory `current` notes.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/keep-summarizing/perspectives.md`

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).

## Self-check

- [ ] The identified conflict, canonical owner, evidence, sensitivity, and authorized resolution are settled by the agent.
- [ ] Each command request has one exact effect and current digest, with explicit content/status/links and no reasoning transcript.
- [ ] Replacement references exist before a supersede/deprecate request; no ad hoc canonical edit or multi-record atomicity was claimed.
- [ ] Report actual written paths and stale/rebuilt projection outcomes without a script-owned merge or acceptance judgment.
