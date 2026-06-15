---
id: rule-ks-persistence-gate
applies_when:
  - knowledge write may occur
enforcement: must
load: conditional
requires: []
---

# Ks Persistence Gate

## Purpose

- Define the enforceable contract for `rule-ks-persistence-gate`.

## Must

- resolve project
- directive
- perspective
- status
- source
- evidence
- and allowed path before writing

## Must Not

- guess missing project
- lifecycle
- status
- or target path

## Validation

- required fields exist
- generated skills cite applicable rule

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
