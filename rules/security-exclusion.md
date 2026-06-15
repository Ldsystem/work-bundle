---
id: rule-work-bundle-security-exclusion
applies_when:
  - v4 work-bundle operation requires security-exclusion
enforcement: must
load: conditional
requires: []
---

# Security Exclusion

## Purpose

- Define the enforceable contract for `rule-work-bundle-security-exclusion`.

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
