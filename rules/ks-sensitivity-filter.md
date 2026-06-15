---
id: rule-ks-sensitivity-filter
applies_when:
  - source content is inspected or written
enforcement: must
load: conditional
requires: []
---

# Ks Sensitivity Filter

## Purpose

- Define the enforceable contract for `rule-ks-sensitivity-filter`.

## Must

- exclude secrets
- credentials
- personal data
- raw chat logs
- and temporary command output

## Must Not

- persist sensitive or raw transcript material

## Validation

- required fields exist
- generated skills cite applicable rule

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
