---
id: rule-work-bundle-runtime-artifact-format
applies_when:
  - v4 work-bundle operation requires runtime-artifact-format
enforcement: must
load: conditional
requires: []
---

# Runtime Artifact Format

## Purpose

- Define the enforceable contract for `rule-work-bundle-runtime-artifact-format`.

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
