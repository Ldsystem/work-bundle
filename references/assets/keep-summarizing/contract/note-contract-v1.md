---
id: <stable-note-id>
title: <specific durable-question title>
lifecycle_stage: tender | investigation | customer_design | bidding | development_design | implementation | deployment | go_live_delivery | operation
perspective: <lifecycle-stage>/<primary leaf perspective path>
status: draft | proposed | confirmed | implemented | current | superseded | deprecated | rejected
source_type: discussion | tender_doc | investigation_note | design_doc | bid_doc | source_code | handoff | plan_review | deployment_record | delivery_record | runtime_observation
summary: <one-sentence retrieval summary>
tags: []
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
evidence:
  - type: specification | plan | handoff | plan_review | source_code | deployment_record | delivery_record | runtime_observation | source_note
    path: <relative-path>
    relation: confirms | implements | derives_from | validates | supersedes | observes
related_notes: []
supersedes: []
superseded_by: []
owner: keep-summarizing
visibility: private
sensitivity: normal | confidential | secret
embedding:
  include: true
  chunk_strategy: heading
---

# <specific durable-question title>

## Summary

State the durable point in one short paragraph.

## Current Facts

List only the effective facts for this lifecycle note.

## Constraints / Rules

List constraints that future agents may apply for this lifecycle note.

## Evidence Notes

Front matter `evidence` is required when evidence affects status, retrieval authority, validation, or promotion. Body evidence may explain rationale, but it does not replace front matter evidence for promoted `confirmed`, `implemented`, or promoted `current` notes.

## Lifecycle Path Normalization

Filesystem paths use hyphenated lifecycle segments while metadata uses underscored enum values:

| Metadata value | Filesystem segment |
|---|---|
| `customer_design` | `customer-design` |
| `development_design` | `development-design` |
| `go_live_delivery` | `go-live-delivery` |

Do not mix styles within the same layer.

## Related Notes
