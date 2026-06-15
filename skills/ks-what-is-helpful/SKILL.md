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

Discovery and classification contract:

- discover relevant candidates across all allowed lifecycle partitions before lifecycle/status authority classification. Lifecycle does not pre-exclude discovery candidates.
- Apply visibility, sensitivity, and scope filters, then load full note bodies only for candidates that may materially affect the task.
- Classify validated candidates as `authority`, `candidate`, `background`, or `blocked`; only `authority` may directly shape downstream requirements, tasks, decisions, or review conclusions.
- Return the smallest useful classified result set rather than bulk-loading or dumping the knowledge base.

Workflow:

1. **Clarify the ask** — restate goal and success criteria; infer likely leaf perspectives from `references/assets/keep-summarizing/perspectives.md`.
2. **Greedy candidate matching** — discover across every allowed lifecycle partition, registry item, perspective index, atomic note, and open-question watchpoint; do not pre-exclude by lifecycle stage or FTS rank; keep output selective (typically 3–12 items).
3. **Minimum necessary loading** — `project.yaml`, `indexes/document-registry.jsonl`, `indexes/open-question-registry.jsonl`, perspective indexes; ignore `context-packs/` unless explicitly requested.
4. **Validate candidates** — read bodies that may materially affect the task; drop weak metadata matches; flag domain rules trapped in implementation notes as extraction gaps.
5. **Classify and rank** — in gateway mode run `scripts/ks.py query --project <slug> --target <retrieval-policy> --query <query> --include-background`; use `retrieval_role` exactly; score by relevance, actionability, authority/trust, and specificity.
6. **Filter noise** — open questions are watch context, not facts; respect visibility/sensitivity; no context packs in normal browsing results.
7. **Surface gaps** — distinguish “no note found” from weak evidence; suggest `ks-extract-valuable-points`, `ks-breakdown-design`, or `ks-track-open-questions` when appropriate.
8. **Offer next steps** — annotated reading order; optional gateway mode when caller supplies retrieval policy.

## Gateway mode

When called by orchestration or when the caller provides a retrieval policy:

1. Resolve the project; rebuild `indexes/knowledge.sqlite` with `scripts/ks.py index --project <slug>` if stale.
2. Discover candidates across all allowed lifecycle partitions; do not prefilter to policy authority stages.
3. Apply filters; load bodies only for material candidates.
4. Run `scripts/ks.py query` and classify by lifecycle, status, and work target.
5. Group by `retrieval_role`; return policy, query, grouped results, omitted/blocked rationale, and watchpoints.
6. Do not convert non-authority results into requirements, tasks, decisions, or review conclusions.

Orchestration callers must use this gateway instead of browsing `.work-bundle/knowledge/**` directly. `orch-execute-plan` is a no-retrieval stage and must not invoke this gateway during execution.

## Return

Structured result with: task summary; recommended knowledge (path, summary, why useful, confidence, retrieval role, status); related watchpoints (labeled watch context); optional topic map; gaps; 2–4 next options.

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

Write only under `.work-bundle/knowledge/` allowed paths; redirect orchestration artifacts to orch-* skills.
