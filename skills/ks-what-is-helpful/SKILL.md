---
name: ks-what-is-helpful
description: 'Retrieve useful durable project knowledge for a concrete task without writing knowledge.'
---

# ks-what-is-helpful

## Scope

Retrieve useful durable project knowledge for a concrete task without writing knowledge.

## Workflow Reference

Use `references/assets/keep-summarizing/workflow.md` as the shared workflow authority.

## Intent

Help the user or orchestrator discover which curated project knowledge is useful for a concrete task or goal, without persisting notes or generating reader-facing documents.

## Trigger phrases

- find useful knowledge
- what do we already know about
- what is in the knowledge base for
- help me find relevant notes
- what is helpful for
- search the knowledge base for
- what should I read before
- what exists about

## Use when

- The user states a task, goal, or question and wants to know what the project knowledge base already contains.
- The user is unsure what is documented because knowledge is split into many small atomic notes.
- The user wants a ranked, explained shortlist of atomic notes or watchpoints to read next.
- Orchestration needs the v3 knowledge gateway for a retrieval policy.

## Do not use when

- The user wants to persist, update, or draft durable notes (`ks-write-knowledge`, `ks-extract-valuable-points`, `ks-breakdown-design`).
- The user wants a reader-facing document, briefing, or report (`orch-create-document`).
- The user wants a handoff or execution artifact (`orch-create-handoff`).

## Required inputs

Resolve or ask for:

- **task goal**: what the user wants to accomplish in one sentence.
- **success criteria**: what “useful” means (decide, implement, review, onboard, debug, etc.).
- **scope** (optional): perspectives, subsystems, features, time range, or files in play.
- **output preference** (optional): brief shortlist, annotated reading order, or topic map.
- **constraints** (optional): audience, language, sensitivity, or “current notes only”.
- **retrieval policy** (gateway mode only): `implementation_spec`, `implementation_plan`, `execution`, `customer_spec`, `bidding`, `deployment`, or `operation`.

If the task goal is vague, ask one clarifying question before broad retrieval.

## Retrieval and gateway

Discovery and classification contract: follow `ks-note-state-authority` (`rules/keep-summarizing/ks-note-state-authority.md`).

Context packs during retrieval: follow `ks-context-pack-policy` (`rules/keep-summarizing/ks-context-pack-policy.md`).

Run the directive workflow in **Retrieval Workflow (skill-owned)**.

## Retrieval Workflow (skill-owned)

1. **Clarify the ask** — restate goal and success criteria; infer likely leaf perspectives from `references/assets/keep-summarizing/perspectives.md`.
2. **Form neutral anchors** — derive query terms from the requested artifact, feature, functionality, component, file, API, schema, workflow, or explicit name. Do not add lifecycle stage, perspective, status, support/oppose, maturity, or policy words unless those words are the subject being changed.
3. **Hybrid candidate matching** — use the approved query surface (`scripts/ks.py query --project <slug> --query <neutral-query> --include-background`) to collect mechanical candidates from SQLite FTS, vector index status, and any bounded expansion that the script exposes. Do not browse JSONL indexes as the exploration surface, and do not pre-exclude by lifecycle stage, status, policy target, vector distance, or FTS rank.
4. **Minimum necessary loading** — use script output, `project.yaml`, and targeted candidate bodies only as needed; follow loaded `ks-context-pack-policy` for context-pack handling. JSONL registries remain maintained derived indexes, not broad agent reading material.
5. **Validate candidates** — read bodies that may materially affect the task; drop weak mechanical matches; flag domain rules trapped in implementation notes as extraction gaps.
6. **Classify and rank** — apply loaded `ks-note-state-authority`; agents classify relevance, authority, polarity, materiality, blocker status, actionability, and specificity. Treat script scores, policy hints, vector status, and trace fields as retrieval mechanics only.
7. **Filter noise** — open questions are watch context, not facts; respect visibility and sensitivity per loaded rules.
8. **Surface gaps** — distinguish “no note found” from weak evidence; suggest `ks-extract-valuable-points`, `ks-breakdown-design`, or `ks-track-open-questions` when appropriate.
9. **Offer next steps** — annotated reading order; optional gateway mode when caller supplies retrieval policy.

### Gateway mode

When called by orchestration or when the caller provides a retrieval policy:

1. Resolve the project; rebuild `indexes/knowledge.sqlite` with `scripts/ks.py index --project <slug>` if stale.
2. Build a neutral query from artifact, feature, functionality, component, file, API, schema, workflow, or explicit-name anchors. A retrieval policy is caller intent for later classification, not a discovery-stage filter.
3. Run `scripts/ks.py query --project <slug> --target <retrieval-policy> --query <neutral-query> --include-background` when a policy is supplied, or omit `--target` in standard discovery. Treat `--target` as `policy_hint`; do not use it to hide discovery candidates.
4. Use the script output only as mechanical candidate and trace evidence: anchors, source paths, lifecycle/status metadata, FTS rank, vector status or distance, fusion rank, and bounded-expansion paths when present. Scripts must not decide semantic relevance, authority, polarity, conflict, materiality, truth confidence, or blocker status.
5. Apply visibility, sensitivity, and scope filters; load bodies only for material candidates.
6. Classify candidates per loaded `ks-note-state-authority` into authority, candidate, background, blocked, supporting, opposing, constraining, irrelevant-with-reason, or watch context as applicable. Agents own this classification; users resolve material conflicts that cannot distinguish stale knowledge from changed intent.
7. Return policy hint, neutral query, mechanical trace summary, agent-grouped results, material omitted or blocked rationale, and watchpoints.
8. Label material candidate, background, blocked, opposing, constraining, or watchpoint evidence that may affect requirements, architecture, workflow, API, persistence, validation, execution behavior, or user-purpose conflict so orchestration callers can surface it as rationale, traceability, conflict evidence, or open-question input.
9. Mark non-material unsettled results as omitted or non-blocking rationale; do not require orchestration callers to resolve them during `create-specification`.
10. Do not convert non-authority results into requirements, tasks, decisions, or review conclusions.

Orchestration callers must use this gateway instead of browsing `.work-bundle/knowledge/**` directly. `orch-execute-plan` is a no-retrieval stage and must not invoke this gateway during execution.

### Ranked shortlist output

Structured result with: task summary; recommended knowledge (path, summary, why useful, agent classification, mechanical trace summary, status); related watchpoints (labeled watch context); optional topic map; gaps; 2–4 next options.

## Return

Deliver the ranked shortlist defined in **Retrieval Workflow (skill-owned)**.

## Runtime Rules

- `ks-knowledge-boundary`: `rules/keep-summarizing/ks-knowledge-boundary.md`
- `ks-context-pack-policy`: `rules/keep-summarizing/ks-context-pack-policy.md`
- `ks-open-question-policy`: `rules/keep-summarizing/ks-open-question-policy.md`
- `ks-note-state-authority`: `rules/keep-summarizing/ks-note-state-authority.md`
- `ks-sensitivity-filter`: `rules/keep-summarizing/ks-sensitivity-filter.md`

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

Durable knowledge boundary: follow `ks-knowledge-boundary` (`rules/keep-summarizing/ks-knowledge-boundary.md`).
