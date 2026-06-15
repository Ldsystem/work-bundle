---
id: rule-integrity-check-script-boundary
applies_when:
  - integrity-check helper CLI commands run
enforcement: must
load: conditional
requires: []
---

# Integrity Check Script Boundary

## Purpose

- Define the enforceable contract for `rule-integrity-check-script-boundary`.

## Must

- helper CLI supports only report lifecycle operations: new, add-issue, update-status, summarize-status, archive-report, validate-report
- validate-report performs structure checks only
- all status updates require reason and evidence for fixed outcomes

## Must Not

- executing project scripts or arbitrary shell commands
- orphan classification authority
- policy interpretation authority
- recommendation generation without agent-authored findings
- finding-correctness validation mode in validate-report

## Validation

- CLI help output contains only approved subcommands
- validate-report rejects finding-correctness mode

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
