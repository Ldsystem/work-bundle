---
id: rule-ks-knowledge-boundary
applies_when:
  - knowledge access or write is requested
enforcement: must
load: conditional
requires: []
---

# Ks Knowledge Boundary

## Purpose

- Define the enforceable contract for `rule-ks-knowledge-boundary`.

## Must

- treat .work-bundle/knowledge as durable source of truth

## Must Not

- write orchestration artifacts as knowledge

## Validation

- required fields exist
- generated skills cite applicable rule

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
