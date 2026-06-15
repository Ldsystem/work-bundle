---
id: rule-ks-perspective-routing
applies_when:
  - note path or perspective is selected
enforcement: must
load: conditional
requires: []
---

# Ks Perspective Routing

## Purpose

- Define the enforceable contract for `rule-ks-perspective-routing`.

## Must

- use the most specific lifecycle-aware leaf perspective

## Must Not

- store durable facts in broad containers or wrong implementation-only homes

## Validation

- required fields exist
- generated skills cite applicable rule

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
