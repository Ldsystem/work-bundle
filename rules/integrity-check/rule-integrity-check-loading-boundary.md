---
id: rule-integrity-check-loading-boundary
applies_when:
  - integrity-check evaluates startup and compression boundaries
enforcement: must
load: conditional
requires: []
---

# Integrity Check Loading Boundary

## Purpose

- Define the enforceable contract for `rule-integrity-check-loading-boundary`.

## Must

- detect and report eager loading that violates startup-minimal context rules
- verify loading boundaries for project metadata, agent entry, role profiles, and roadmap files
- classify loading issues with explicit risk level and concrete remediation action

## Must Not

- forcing startup to load full roadmap, full project metadata, all role profiles, all notes, all rules, or all skill references

## Validation

- report includes compression/loading section and startup-loading matrix
- findings include runtime_loading_risk and recommended_action fields

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
