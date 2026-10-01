---
name: ks-track-open-questions
description: 'Persist user-confirmed future-work watchpoints as accepted open questions.'
---

# ks-track-open-questions

## Scope

Persist user-confirmed future-work watchpoints as accepted open questions.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Track accepted unresolved project questions as standalone watchpoints under `open-questions/`.

## Trigger phrases

- record it for later
- we will resolve it later
- track this open question
- future problem to fix

## Use when

- the user provides a question as future work
- the user confirms an agent-proposed question should be tracked
- the user says `record it`, `we will resolve it later`, or similar

## Do not use when

Speculative questions the user has not accepted.

## Required inputs

- Question text and perspective.
- Trigger terms for future matching.
- User confirmation when the question was agent-proposed.

## Workflow

1. Run structural-value test (see `ks-structural-value`).
2. Apply open-question policy per loaded `ks-open-question-policy`.
3. Complete watchpoint front matter per **Open Question Constraints (skill-owned)**.
4. Complete the shared workflow's agent decision preconditions. Prepare one `effect: create`, `kind: open-question` request with absent canonical knowledge-relative `path`, `expected_digest: null`, complete `record` front matter, and exact Markdown `body`; initial status is `open` and unresolved fields are explicit nulls.
5. Invoke `python3 scripts/ks.py mutate-knowledge --project <slug> --request-file <request.yaml>` with optional `--dry-run`. Do not directly create the watchpoint or patch the registry. Consume the returned canonical/projection outcomes and existing stale-projection rebuild command.

## Strict Rules

Apply loaded Runtime Rules:

- Open-question confirmation and watchpoint policy: follow `ks-open-question-policy`
- Structural-value gate: follow `ks-structural-value`
- Knowledge path and scope: follow `ks-knowledge-boundary`
- Persistence gates: follow `ks-persistence-gate`
- Note and watchpoint state: follow `ks-note-state-authority`
- Index completion: follow `ks-index-maintenance`
- Sensitivity exclusions: follow `ks-sensitivity-filter`

## Return

- open-question ID
- target path under `open-questions/`
- perspective
- trigger terms
- why it should be tracked
- whether indexes were rebuilt

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-persistence-gate`: `rules/keep-summarizing/ks-persistence-gate.md`
- `ks-open-question-policy`: `rules/keep-summarizing/ks-open-question-policy.md`
- `ks-note-state-authority`: `rules/keep-summarizing/ks-note-state-authority.md`
- `ks-index-maintenance`: `rules/keep-summarizing/ks-index-maintenance.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`
- `ks-structural-value`: `rules/keep-summarizing/ks-structural-value.md`

Central `AGENTS.md` owns indexed rule discovery and exact-context body reuse. Consume carried task-local obligations in an accepted worker packet; these Runtime Rules are procedural pointers, not a separate loading algorithm.

## Open Question Constraints (skill-owned)

- Use only leaf perspectives under `open-questions/<lifecycle-stage>/<perspective>/`.
- Require trigger terms in front matter before completion.
- Complete watchpoint front matter: question text, perspective, trigger terms, and tracking rationale.
- Derive concrete trigger terms from the accepted watchpoint when possible; return `Waiting for your direction` only when the intended future match remains unclear.

## Scripts

Use `scripts/ks.py` when deterministic helper behavior is needed.

## Boundary

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).

## Self-check

- [ ] User-confirmed tracking intent, structural value, relevance, authority, conflicts, sensitivity, and evidence are settled.
- [ ] The complete request declares one absent watchpoint, exact content/front matter and links, with no internal reasoning fields.
- [ ] The command performed creation; the watchpoint remains watch context rather than settled facts.
- [ ] Canonical and index outcomes are reported separately; successful indexing does not qualify the question's meaning.
