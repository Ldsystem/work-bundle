---
id: rule-ks-index-maintenance
applies_when:
  - durable notes or open questions changed
enforcement: must
load: conditional
requires: []
---

# Ks Index Maintenance

## Purpose

- Define the enforceable contract for `rule-ks-index-maintenance`.

## Must

- rebuild derived document and open-question indexes before completion

## Must Not

- hand-edit generated indexes or leave stale indexes

## Validation

- required fields exist
- generated skills cite applicable rule

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
