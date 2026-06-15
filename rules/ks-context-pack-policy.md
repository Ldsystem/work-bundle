---
id: rule-ks-context-pack-policy
applies_when:
  - context packs are requested
enforcement: must
load: conditional
requires: []
---

# Ks Context Pack Policy

## Purpose

- Define the enforceable contract for `rule-ks-context-pack-policy`.

## Must

- treat context packs as temporary scaffolding and prefer canonical notes for authority

## Must Not

- use stale context packs as normal authority

## Validation

- required fields exist, generated skills cite applicable rule

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
