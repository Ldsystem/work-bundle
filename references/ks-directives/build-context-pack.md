# build-context-pack

## Intent

Build compact context packs for future agents under `context-packs/`.

## Trigger phrases

- build context pack
- update current context
- agent context for this project

## Use when

The user wants temporary agent scaffolding derived from durable notes.

## Do not use when

The user only wants a one-off reading list (`what-is-helpful`) or a handoff request for `orchestrator` `create-handoff`.

## Required inputs

- Project slug.
- Current goal and stable assumptions.
- Optional: scope of perspectives to include.

## Workflow

1. Gather current goal, assumptions, flows, architecture, conventions, decisions, non-goals, and risks from curated notes.
2. Treat atomic perspective notes as authoritative. Do not make the context pack the only home for any durable rule.
3. Write or update `context-packs/current.md` (or named pack).
4. Add or update expiry metadata or a visible review note when the pack should be refreshed.
5. Avoid raw logs, excessive history, temporary debugging, and stale assumptions.
6. If a context pack remains useful after 30 days, refresh it from canonical notes or decompose its stable content into atomic notes.

## Rules

- Context packs are temporary scaffolding for agent startup, not canonical knowledge.
- Normal knowledge browsing should ignore context packs unless the user explicitly asks for context-pack work.
- Do not duplicate large note bodies into a context pack; summarize and link to canonical notes.
- If the pack contains facts not present in canonical notes, extract those facts before treating them as durable.

## Return

- path to the context pack
- what was included and excluded
- whether indexes need rebuild
