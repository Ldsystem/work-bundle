---
name: ks-resolve-open-question
description: 'Resolve or update an existing accepted watchpoint when discussion answers or materially changes it; split only under authorized new-record intent. Excludes tracking a new question.'
---

# ks-resolve-open-question

## Scope

Resolve, update, split, or keep accepted open-question watchpoints.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Resolve or update an existing open-question watchpoint.

## Trigger phrases

- resolve this open question
- close the watchpoint
- update open question

## Use when

Current discussion answers or materially changes an open question.

## Do not use when

No matching open question exists (use `ks-track-open-questions` to create one).

## Workflow

1. Apply open-question policy per loaded `ks-open-question-policy`.
2. Complete the shared workflow's agent decision preconditions and resolve the intended effect per **Resolution Constraints (skill-owned)**. Honor an explicit authorized answer/update without repeating the choice menu.
3. Prepare a complete `kind: open-question` request with `effect: resolve-open-question` for `open` to `resolved`, or `effect: update` for content at the same status. Include exact `path`, current `expected_digest`, complete `record`, and `body`; declared resolution date/summary and optional existing note link belong in front matter.
4. Invoke `python3 scripts/ks.py mutate-knowledge --project <slug> --request-file <request.yaml>` with optional `--dry-run`. Do not patch watchpoint YAML/Markdown or the registry directly. Report canonical and projection outcomes; use the returned existing rebuild command only when needed.

## Return

- question ID and new status
- resolution summary when resolved
- index rebuild status

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-open-question-policy`: `rules/keep-summarizing/ks-open-question-policy.md`
- `ks-note-state-authority`: `rules/keep-summarizing/ks-note-state-authority.md`
- `ks-index-maintenance`: `rules/keep-summarizing/ks-index-maintenance.md`

Central `AGENTS.md` owns indexed rule discovery and exact-context body reuse. Consume carried task-local obligations in an accepted worker packet; these Runtime Rules are procedural pointers, not a separate loading algorithm.

## Resolution Constraints (skill-owned)

When the intended action is unresolved, ask the user to choose:

1. Mark resolved and record the accepted answer.
2. Keep open and append current context.
3. Split into a new open question.
4. Ignore for now.

For the declared resolved record:

- set `status: resolved`
- add `resolved_at`
- add `resolution_summary`
- optionally set `resolved_by_note_id`

A split requires separately authorized new-watchpoint intent through `ks-track-open-questions`; the existing record and the new one are separate one-record effects. Keeping/ignoring without a content change does not invoke a mutation.

Resolution policy: follow loaded `ks-open-question-policy` for confirmation, durable-note conversion, and watchpoint history.

When waiting for the user:

```text
Waiting for your direction.

Choose one:
1. Mark resolved and record the accepted answer.
2. Keep open and append current context.
3. Split into a new open question.
4. Ignore for now.

Recommended: 1 when the answer is accepted and stable.
```

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).

## Self-check

- [ ] An existing accepted watchpoint and explicit resolution/update intent are identified; no redundant menu follows settled authority.
- [ ] Agent meaning, relevance, evidence, conflicts, and sensitivity are settled before the one-record request.
- [ ] Complete front matter, content, digest, and declared links were supplied to the command, without a reasoning transcript.
- [ ] Actual canonical/projection effects are reported separately, and any split used separately authorized creation.
