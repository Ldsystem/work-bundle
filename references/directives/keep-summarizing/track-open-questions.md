# track-open-questions

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
- the user says `record it`, `we will resolve it later`, `we will talk about it later`, or similar

## Do not use when

Speculative questions the user has not accepted.

## Required inputs

- Question text and perspective.
- Trigger terms for future matching.
- User confirmation when the question was agent-proposed.

## Workflow

1. Run structural-value test.
2. Write standalone note under `open-questions/<lifecycle-stage>/<perspective>/`.
3. Rebuild `indexes/open-question-registry.jsonl`.

## Strict Rules

- Do not persist agent-generated questions without explicit user confirmation.
- Do not store open questions inside durable notes.
- Do not label an open question as a fact, decision, or rule.
- Use only leaf perspectives.
- Require trigger terms before completion so future work can match the watchpoint.
- If confirmation or trigger terms are missing, return `Waiting for your direction`.

## Return

- open-question ID
- target path under `open-questions/`
- perspective
- trigger terms
- why it should be tracked
- whether indexes were rebuilt
