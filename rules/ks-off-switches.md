---
id: rule-ks-off-switches
applies_when:
  - user disables persistence or asks draft only
enforcement: must
load: conditional
requires: []
---

# Ks Off Switches

## Purpose

- Define the enforceable contract for `rule-ks-off-switches`.

## Must

- stop durable writes and report waiting state when off-switches apply

## Must Not

- persist despite explicit pause
- draft-only
- or stop instruction

## Validation

- required fields exist
- generated skills cite applicable rule

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
