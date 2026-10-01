---
id: ks-index-maintenance
applies_when:
  - managed durable notes, accepted context packs, or open questions change
  - completion follows a canonical note or open-question mutation
  - a user requests regeneration of stale, missing, or deleted derived knowledge indexes
enforcement: must
load: conditional
requires: []
---

# Keep-Summarizing Index Maintenance

## Purpose

Define the completion gate for derived keep-summarizing indexes. Indexed artifacts are reproducible outputs from curated Markdown, so note or open-question work is not complete until the relevant indexes are rebuilt or any rebuild issue is surfaced.

## Must

- rebuild derived document, search, vector, and open-question indexes before completion when relevant content changed
- treat indexes as disposable artifacts that must be reproducible from Markdown
- keep the generated index set aligned with current curated Markdown and accepted open-question state
- include these derived files in index maintenance scope when relevant:
  - `indexes/document-registry.jsonl`
  - `indexes/chunk-registry.jsonl`
  - `indexes/backlink-map.json`
  - `indexes/embedding-manifest.json`
  - `indexes/knowledge.sqlite`
  - vector tables or vector-sidecar artifacts maintained in or beside `indexes/knowledge.sqlite`
  - `indexes/open-question-registry.jsonl`
- report vector index status as derived/disposable output (`rebuilt`, `unavailable`, `skipped`, or `failed`) before claiming completion
- surface any reported rebuild issue before claiming completion
- Consume a successful mutation command's rebuild outcome instead of rerunning the same index work. If projection rebuilding fails after canonical replacement, preserve the valid Markdown record, report the projection as stale/regenerable, and use the returned existing rebuild command.

## Must Not

- hand-edit generated indexes
- hide stale indexes after durable note accepted context-pack or open-question changes
- claim completion after a note or open-question write before the relevant index rebuild has run
- treat disposable index outputs as canonical knowledge instead of Markdown-derived artifacts
- treat vector similarity, embedding artifacts, or mechanical ranks as truth, authority, or conflict resolution
- roll back valid canonical content, patch generated indexes, or invalidate its semantic meaning merely because projection rebuilding failed

## Validation

- required index rebuild runs before completion when curated Markdown or open questions changed
- generated index files match the documented derived set when relevant to the change
- vector index artifacts or explicit vector-unavailable status are reported with the rebuild result
- any rebuild problem is surfaced instead of hidden behind a completion claim
- no manual edits are used to patch generated index state

## On Violation

Report which derived index is stale missing or manually altered and regenerate it from canonical Markdown through the existing rebuild command. Report an already applied canonical replacement separately from unresolved projection recovery; do not claim the index is current while rebuilding remains unsuccessful.
