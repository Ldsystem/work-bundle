---
id: ks-note-state-authority
applies_when:
  - knowledge note state affects retrieval or persistence authority
enforcement: must
load: conditional
requires: []
---

# Keep-Summarizing Note State Authority

## Purpose

Define the retrieval and persistence authority contract for lifecycle-aware knowledge notes. Discovery must stay broad enough to surface relevant candidates, while downstream work must use classified authority narrowly and explicitly.

## Must

- discover relevant candidates across allowed lifecycle partitions before authority classification
- run gateway retrieval in this order: discover fully, load minimally, classify explicitly, use authority narrowly, and return selectively
- apply visibility, sensitivity, and scope filtering before minimum necessary full-body validation
- load full note bodies only for materially relevant candidates and only to the minimum extent needed for classification
- classify validated candidates as authority candidate background or blocked for the work target
- use only authority to shape requirements tasks decisions or review conclusions
- surface relevant non-authority results with uncertainty or incompatibility
- preserve lifecycle-aware durable write ownership

## Must Not

- prefilter relevant discovery candidates by authority lifecycle or note status
- skip explicit classification after candidate discovery and minimal validation
- load broad note bodies before candidate relevance justifies full-body validation
- promote non-authority notes to stable facts silently
- let FTS rank recency or lifecycle proximity override authority
- hide note-state uncertainty inside assumptions

## Validation

- retrieval discovers relevant cross-lifecycle candidates before authority narrowing
- retrieval output separates authority candidate background blocked context
- gateway flow shows minimal full-body loading before lifecycle and status classification
- only authority shapes downstream work
- uncertain helpful notes are surfaced as uncertainty
- durable write decisions preserve lifecycle-aware ownership instead of treating retrieval visibility as write authority

## On Violation

Stop the retrieval or persistence operation, report which discovery, classification, or authority-use step was skipped or misapplied, and make the minimal correction before continuing.
