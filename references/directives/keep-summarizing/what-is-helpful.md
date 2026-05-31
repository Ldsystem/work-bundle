# what-is-helpful

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
- `orchestrator` needs the v3 knowledge gateway for a directive-specific retrieval policy.

## Do not use when

- The user wants to persist, update, or draft durable notes (`write-knowledge`, `extract-valuable-points`, `breakdown-design`).
- The user wants a reader-facing document, briefing, or report (use `orchestrator` `create-document`).
- The user wants a handoff or execution artifact (use `orchestrator` `create-handoff`).
- The user only wants directive selection help (`help-with-directives`).

## Required inputs

Resolve or ask for:

- **task goal**: what the user wants to accomplish in one sentence.
- **success criteria**: what “useful” means for this request (decide, implement, review, onboard, debug, etc.).
- **scope** (optional): perspectives, subsystems, features, time range, or files in play.
- **output preference** (optional): brief shortlist, annotated reading order, or topic map.
- **constraints** (optional): audience, language, sensitivity, or “current notes only”.
- **retrieval policy** (gateway mode only): `implementation_spec`, `implementation_plan`, `execution`, `customer_spec`, `bidding`, `deployment`, or `operation`.

If the task goal is vague, ask one clarifying question before broad retrieval.

## Workflow

1. **Clarify the ask**
   - Restate the task goal and success criteria in your own words.
   - Infer likely lifecycle-aware leaf perspectives from `references/ks-perspectives.md` (`development-design/architecture/decisions`, `development-design/workflow/data-flow`, `development-design/workflow/process-flow`, `implementation/module-structure`, etc.).

2. **Greedy candidate matching**
   - Treat matching as greedy within the declared task purpose: investigate every registry item, perspective index, atomic note, and open-question watchpoint that might plausibly help the current goal.
   - Do not stop after the first strong match when nearby notes, related perspectives, tags, titles, source paths, or trigger terms may contain useful context.
   - Use keyword, metadata, perspective, link, and vector discovery as candidate finders, then validate candidates against registry metadata, lifecycle, front matter, and note bodies before recommending them.
   - Keep the final output selective: greedy matching expands the candidate set, not the returned reading list.
   - Ignore `context-packs/` during normal browsing. Load them only when the user explicitly asks to inspect, refresh, migrate, decompose, or build context packs.

3. **Minimum necessary loading** (load enough to validate candidates without dumping the knowledge base)
   - `project.yaml` for project identity, allowed roots, lifecycle, and sensitivity rules.
   - `indexes/document-registry.jsonl` for note titles, paths, perspectives, tags, and status.
   - `indexes/open-question-registry.jsonl` for watch context only (not as facts).
   - Perspective-level indexes or note listing under matched `notes/<lifecycle-stage>/<leaf-perspective>/` paths.
   - Vector or keyword discovery only to find candidates; confirm against registry metadata and note front matter before recommending.

4. **Validate candidate content**
   - Read full note bodies for candidates that may materially affect the task, decision, plan, review, or implementation context.
   - Pull linked related notes when a candidate explicitly references them.
   - Drop candidates whose body content does not support the apparent metadata match.
   - If an implementation or interface note contains the only visible copy of a domain rule, mark that as a gap or extraction candidate instead of treating the implementation-shaped note as the canonical source.
   - If duplicate full-body notes cover the same durable fact, recommend only the canonical or best-owned perspective and mention duplicate drift as a maintenance issue.
   - Stop expanding after every plausible candidate path has been checked enough to explain what is known, what is uncertain, and what is missing.

5. **Classify and rank candidates**
   - In gateway mode, run `scripts/ks.py query --project <slug> --target <retrieval-policy> --query <query> --include-background`.
   - Use returned `retrieval_role` exactly as the role label: `authority`, `candidate`, `background`, or `blocked`.
   - `authority` may shape downstream artifacts. `candidate`, `background`, and `blocked` must be kept separate and must not become requirements, tasks, or decisions without promotion.
   - In discovery mode, provide confidence labels for human reading, but do not replace v3 retrieval roles when a retrieval policy is provided.
   Score each item by:
   - **relevance**: directly answers the task goal or a sub-question.
   - **actionability**: helps the user decide or act next.
   - **authority/trust**: prefer `authority` over `candidate`; use `confirmed`, `implemented`, and `current` as default authority statuses; treat `superseded`, `deprecated`, and `rejected` as blocked or historical unless explicitly requested.
   - **specificity**: prefer the most specific leaf perspective over broad container topics.

6. **Filter out noise**
   - Do not treat open questions as established facts.
   - Do not recommend duplicate notes covering the same point; pick the best one and mention alternates briefly.
   - Do not recommend context packs in normal browsing results; list stale or still-useful packs as maintenance gaps only when discovered through explicit context-pack work.
   - Respect `visibility`, `sensitivity`, and lifecycle in `project.yaml`.
   - Do not dump the whole knowledge base; return the smallest useful set (typically 3–12 items).

7. **Surface gaps**
   - State what the knowledge base does **not** cover for this task.
   - Distinguish “no note found” from “only draft or weak evidence exists”.
   - Suggest whether to run `extract-valuable-points`, `breakdown-design`, or `track-open-questions` if the user may want to fill gaps later.

8. **Offer next steps** (read-only by default)
   - Annotated reading order.
   - Optional: switch to gateway mode if the caller supplies an orchestrator retrieval policy.
   - Optional: persist new knowledge only if the user explicitly asks.

## Gateway mode

Use this mode when called by `orchestrator` or when the caller provides a retrieval policy.

Required behavior:

1. Resolve the project and ensure `indexes/knowledge.sqlite` is current; if not, rebuild with `scripts/ks.py index --project <slug>`.
2. Run `scripts/ks.py query --project <slug> --target <retrieval-policy> --query <task query> --include-background`.
3. Group results by `retrieval_role`.
4. Return `retrieval_policy`, query, grouped results, omitted/blocked rationale, and related open-question watchpoints.
5. Do not convert non-authority results into requirements, tasks, or durable decisions.

## Return

Return a structured result:

- **task summary**: restated goal and success criteria.
- **recommended knowledge** (ordered list), each with:
  - note path or ID
  - one-line summary
  - why it is useful for this task
  - discovery confidence: high | medium | low
  - retrieval role when a policy is used: authority | candidate | background | blocked
  - lifecycle status when relevant
- **related watchpoints**: matched open questions with trigger terms (labeled as watch context, not facts).
- **topic map** (optional): perspectives or themes covered vs missing.
- **gaps**: what is not documented or only weakly supported.
- **next options**: 2–4 concrete choices (e.g. read these three notes, expand search to X, persist findings, redirect to `orchestrator`).

Example response shape:

```text
Task: Add rate limiting to the public API.

Recommended knowledge (read in this order):
1. notes/development-design/architecture/component-boundary/api-gateway.md — defines gateway boundaries and extension points. (high, current)
2. notes/development-design/architecture/decisions/rate-limit-strategy.md — accepted token-bucket approach for public routes. (high, current)
3. notes/implementation/module-structure/api-limiter.md — shows where the limiter plugs in; validate domain rules against canonical architecture/data notes. (medium)

Watch context (not facts):
- open-questions/development-design/architecture/decisions/redis-failover.md — may affect limiter storage choice.

Gaps:
- No note on per-tenant quota configuration.

Next options:
1. I can summarize these three notes for implementation planning.
2. Expand search to `development-design/workflow/process-flow` and `implementation/module-structure`.
3. Persist a new note after you confirm the tenant quota approach.
```

## Relationship to other directives

- **`what-is-helpful`**: user-facing discovery; optimize for clarity, coverage map, and explained recommendations.
- **`help-with-directives`**: meta help about which directive to use, not knowledge search.
