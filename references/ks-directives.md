# keep-summarizing Directives

Use this file to **select** a directive. Load only the chosen directive file from `references/ks-directives/<name>.md` unless the user needs a comparison across directives.

Modular directives are internal behavior modules, not separate skills.

## Quick selection

| User intent | Directive | File |
| --- | --- | --- |
| Which directive should I use? | `help-with-directives` | [help-with-directives.md](ks-directives/help-with-directives.md) |
| I want to do X — what knowledge helps? | `what-is-helpful` | [what-is-helpful.md](ks-directives/what-is-helpful.md) |
| Extract + perspective-breakdown from chat/session | `extract-valuable-points` | [extract-valuable-points.md](ks-directives/extract-valuable-points.md) |
| Should this be saved? | `detect-structural-update` | [detect-structural-update.md](ks-directives/detect-structural-update.md) |
| Write or update notes | `write-knowledge` | [write-knowledge.md](ks-directives/write-knowledge.md) |
| Rebuild indexes | `maintain-indexes` | [maintain-indexes.md](ks-directives/maintain-indexes.md) |
| Merge or resolve note conflicts | `resolve-conflicts` | [resolve-conflicts.md](ks-directives/resolve-conflicts.md) |
| Build agent context pack | `build-context-pack` | [build-context-pack.md](ks-directives/build-context-pack.md) |
| Break down a design file | `breakdown-design` | [breakdown-design.md](ks-directives/breakdown-design.md) |
| Track accepted future question | `track-open-questions` | [track-open-questions.md](ks-directives/track-open-questions.md) |
| Resolve or update open question | `resolve-open-question` | [resolve-open-question.md](ks-directives/resolve-open-question.md) |
| Change note lifecycle status | `manage-lifecycle` | [manage-lifecycle.md](ks-directives/manage-lifecycle.md) |
| Enforce scope and sensitivity | `guard-scope` | [guard-scope.md](ks-directives/guard-scope.md) |
| Reader-facing doc from knowledge | `orchestrator create-document` | redirect from keep-summarizing |
| Handoff artifact | `orchestrator create-handoff` | redirect from keep-summarizing |

## Decision tree

```text
User asks about the skill itself?
  → help-with-directives

User wants to FIND useful knowledge for a task (discovery, map, reading list)?
  → what-is-helpful

An orchestrator directive needs v3 retrieval-policy context?
  → what-is-helpful (gateway mode)

User has a design file to decompose into notes?
  → breakdown-design

User wants to SAVE or UPDATE durable knowledge?
  → extract-valuable-points → detect-structural-update → write-knowledge
  → maintain-indexes (after writes)

User mentions a future problem to track?
  → track-open-questions / resolve-open-question

User wants a report, speech, briefing, or human-readable doc?
  → orchestrator create-document

User wants a handoff for another agent/session?
  → orchestrator create-handoff
```

## Boundary rules

- **Discovery vs persistence**: `what-is-helpful` is read-only by default. Do not write notes unless the user explicitly requests persistence.
- **Discovery vs gateway mode**: Use normal `what-is-helpful` output when the user needs an explained map; use gateway mode when an orchestrator directive needs retrieval-policy results with authority, candidate, background, and blocked roles.
- **Knowledge vs orchestration**: Do not create files under `.work-bundle/orchestration/` from keep-summarizing; redirect to `orchestrator`.
- **Facts vs watchpoints**: Open questions inform what to watch; never state them as settled project facts.

## Directive Selection Rules

- Select exactly one primary directive before doing substantive work.
- If the request includes multiple intents, sequence directives explicitly instead of blending them.
- Use `what-is-helpful` for read-only discovery; it must not write.
- Use `extract-valuable-points` before `write-knowledge` when source material is messy or mixed with temporary content.
- Use `write-knowledge` only after the target project, target leaf perspective, lifecycle status, and persistence signal are clear.
- Use `breakdown-design` for design files; it must return a coverage report before persistence.
- Use `track-open-questions` only for user-provided or user-confirmed future work.
- Redirect reader-facing documents, specifications, plans, execution state, and handoffs to `orchestrator`.
- If no directive fits cleanly, use `help-with-directives` and ask for direction.

## All directive files

- [help-with-directives.md](ks-directives/help-with-directives.md)
- [what-is-helpful.md](ks-directives/what-is-helpful.md)
- [extract-valuable-points.md](ks-directives/extract-valuable-points.md)
- [detect-structural-update.md](ks-directives/detect-structural-update.md)
- [build-context-pack.md](ks-directives/build-context-pack.md)
- [write-knowledge.md](ks-directives/write-knowledge.md)
- [maintain-indexes.md](ks-directives/maintain-indexes.md)
- [resolve-conflicts.md](ks-directives/resolve-conflicts.md)
- [breakdown-design.md](ks-directives/breakdown-design.md)
- [track-open-questions.md](ks-directives/track-open-questions.md)
- [resolve-open-question.md](ks-directives/resolve-open-question.md)
- [manage-lifecycle.md](ks-directives/manage-lifecycle.md)
- [guard-scope.md](ks-directives/guard-scope.md)
