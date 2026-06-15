---
id: rule-ks-open-question-policy
applies_when:
  - future work or unresolved question is handled
enforcement: must
load: conditional
requires: []
---

# Ks Open Question Policy

## Purpose

- Define the enforceable contract for `rule-ks-open-question-policy`.

## Must

- persist only user-provided or user-confirmed open-question watchpoints

## Must Not

- treat open questions as settled facts

## Validation

- required fields exist
- generated skills cite applicable rule

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
