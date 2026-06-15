---
id: rule-ks-note-state-authority
applies_when:
  - knowledge note state affects retrieval or persistence authority
enforcement: must
load: conditional
requires: []
---

# Ks Note State Authority

## Purpose

- Define the enforceable contract for `rule-ks-note-state-authority`.

## Must

- discover relevant candidates across allowed lifecycle partitions before authority classification
- classify validated candidates as authority candidate background or blocked for the work target
- use only authority to shape requirements tasks decisions or review conclusions
- surface relevant non-authority results with uncertainty or incompatibility
- preserve lifecycle-aware durable write ownership

## Must Not

- prefilter relevant discovery candidates by authority lifecycle or note status
- promote non-authority notes to stable facts silently
- let FTS rank recency or lifecycle proximity override authority
- hide note-state uncertainty inside assumptions

## Validation

- retrieval discovers relevant cross-lifecycle candidates
- retrieval output separates authority candidate background blocked context
- only authority shapes downstream work
- uncertain helpful notes are surfaced as uncertainty

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
