---
id: ks-doctor-readonly
applies_when:
  - user invokes ks-doctor or keep-summarizing read-only diagnostics
enforcement: must
load: conditional
requires: []
---

# Keep-Summarizing Doctor Read-Only

## Purpose

Enforcement pointer for `ks-doctor`. Full Must/Must Not live in `skills/ks-doctor/SKILL.md`.

## Must

- Before work, load and follow `skills/ks-doctor/SKILL.md` read-only constraints in addition to this citation.
- Remain registered in `rules/index.yaml` with front matter mirroring `wb-create-rule` contract.

## Must Not

- Treat this pointer stub as a substitute for the skill-owned read-only constraints.

## Validation

- Confirm the skill file contains `## Read-Only Constraints (skill-owned)` with enforceable Must/Must Not.

## On Violation

Stop the doctor run, load the skill-owned constraints, and rerun doctor in read-only mode before presenting results.
