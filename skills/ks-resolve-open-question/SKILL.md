---
name: ks-resolve-open-question
description: 'Resolve, update, split, or keep accepted open-question watchpoints.'
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
- Do not convert a resolved answer into a durable note unless the user asks or the answer passes `ks-write-knowledge`.
- Keep the open-question file as the watchpoint history.
- If the answer changes durable project behavior, propose a linked note update separately.

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
