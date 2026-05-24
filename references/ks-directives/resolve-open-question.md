# resolve-open-question

## Intent

Resolve or update an existing open-question watchpoint.

## Trigger phrases

- resolve this open question
- close the watchpoint
- update open question

## Use when

Current discussion answers or materially changes an open question.

## Do not use when

No matching open question exists (`track-open-questions` to create one).

## Workflow

Ask the user to choose:

1. Mark resolved and record the accepted answer.
2. Keep open and append current context.
3. Split into a new open question.
4. Ignore for now.

When resolved:

- set `status: resolved`
- add `resolved_at`
- add `resolution_summary`
- optionally set `resolved_by_note_id`
- rebuild `indexes/open-question-registry.jsonl`

Strict rules:

- Do not mark resolved unless the answer is accepted and stable.
- Do not convert a resolved answer into a durable note unless the user asks or the answer passes `write-knowledge`.
- Keep the open-question file as the watchpoint history.
- If the answer changes durable project behavior, propose a linked note update separately.

When waiting for the user, use this shape:

```text
Waiting for your direction.

Choose one:
1. Mark resolved and record the accepted answer.
2. Keep open and append current context.
3. Split into a new open question.
4. Ignore for now.

Recommended: 1 when the answer is accepted and stable.
```

## Return

- question ID and new status
- resolution summary when resolved
- index rebuild status
