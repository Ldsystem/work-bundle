---
id: rule-integrity-check-report-lifecycle
applies_when:
  - integrity report is created or updated
enforcement: must
load: conditional
requires: []
---

# Integrity Check Report Lifecycle

## Purpose

- Define the enforceable contract for `rule-integrity-check-report-lifecycle`.

## Must

- report status uses only: draft, active, partially_fixed, closed, superseded
- issue status uses only: open, fixed, dismissed, converted, superseded
- report may close only when all issues are non-open
- each issue transition records timestamp, actor, from, to, reason, and evidence

## Must Not

- overwrite previous generated report by default
- close report with open issues

## Validation

- report structure contains metadata, status history, issue summary, and closure checklist
- status sidecar and issue sidecar remain synchronized with report status values

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
