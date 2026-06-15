---
id: rule-integrity-check-agent-authority
applies_when:
  - wb-integrity-check runs
enforcement: must
load: conditional
requires: []
---

# Integrity Check Agent Authority

## Purpose

- Define the enforceable contract for `rule-integrity-check-agent-authority`.

## Must

- agent owns integrity judgment, severity assignment, ownership classification, and fix recommendations
- script outputs may include risk signals and evidence only
- final accept/reject/escalation decisions are human-owned

## Must Not

- script-level policy authority
- script-level integrity correctness authority
- script auto-close of issues without agent or user evidence

## Validation

- report recommendations include agent-authored rationale
- script output marks final decision owner as human

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
