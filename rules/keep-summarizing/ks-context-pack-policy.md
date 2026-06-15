---
id: ks-context-pack-policy
applies_when:
  - context packs are requested
  - context-pack maintenance or migration is performed
enforcement: must
load: conditional
requires: []
---

# Keep-Summarizing Context Pack Policy

## Purpose

Define how context packs may be used without turning temporary startup scaffolding into durable authority. Context packs can help agent startup and maintenance work, but canonical notes remain the durable source of truth.

## Must

- treat context packs as temporary scaffolding and prefer canonical notes for authority
- load context packs only when the user explicitly asks to inspect refresh migrate decompose or build context packs
- if a context pack is still useful after 30 days, break it down into atomic perspective notes or refresh it from current canonical notes
- prefer atomic notes when a context pack duplicates canonical note content
- treat accepted context packs as secondary helper material that must stay traceable back to current canonical notes

## Must Not

- use context-packs as an authority during normal knowledge browsing
- use stale context packs as normal authority
- keep a context pack in active use past the 30-day stale threshold without refreshing or decomposing it
- copy context-pack prose into retrieval output unless the task is specifically about context-pack maintenance
- let duplicated context-pack text outrank canonical notes during retrieval or persistence decisions

## Validation

- context-pack use is tied to an explicit inspect refresh migrate decompose or build request
- retrieval and persistence decisions cite canonical notes instead of context packs as authority
- any still-useful pack older than 30 days is refreshed from canonical notes or decomposed into atomic notes
- duplicated context-pack content is marked stale scaffolding rather than treated as normal authority

## On Violation

Stop the context-pack workflow, report whether the problem is unauthorized authority use, stale scaffolding, or duplication drift, and refresh decompose or fall back to canonical notes before continuing.
