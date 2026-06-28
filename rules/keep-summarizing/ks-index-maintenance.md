---
id: ks-index-maintenance
applies_when:
  - durable notes accepted context packs or open questions change
  - completion follows a note or open-question write
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

## Must Not

- hand-edit generated indexes
- leave stale indexes after durable note accepted context-pack or open-question changes
- claim completion after a note or open-question write before the relevant index rebuild has run
- treat disposable index outputs as canonical knowledge instead of Markdown-derived artifacts
- treat vector similarity, embedding artifacts, or mechanical ranks as truth, authority, or conflict resolution

## Validation

- required index rebuild runs before completion when curated Markdown or open questions changed
- generated index files match the documented derived set when relevant to the change
- vector index artifacts or explicit vector-unavailable status are reported with the rebuild result
- any rebuild problem is surfaced instead of hidden behind a completion claim
- no manual edits are used to patch generated index state

## On Violation

Stop completion, report which derived index is stale missing or manually altered, rebuild the relevant indexes from Markdown, and only then resume completion reporting.
