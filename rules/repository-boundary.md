---
id: rule-work-bundle-repository-boundary
applies_when:
  - v4 work-bundle operation requires repository-boundary
enforcement: must
load: conditional
requires: []
---

# Repository Boundary

## Purpose

- Define the enforceable contract for `rule-work-bundle-repository-boundary`.

## Must

- follow source authority
- keep runtime files compact

## Must Not

- do not generate .mdc files
- do not include raw logs or secrets

## Validation

- required fields exist
- scope is work-bundle

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
