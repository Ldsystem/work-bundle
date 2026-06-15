---
id: orch-doctor-readonly
applies_when:
  - user invokes orch-doctor or the doctor directive
  - orchestrator read-only diagnostics are requested
enforcement: must
load: conditional
requires: []
---

# Orchestration Doctor Read-Only

## Purpose

Enforcement pointer for `orch-doctor`. Full Must/Must Not live in `skills/orch-doctor/SKILL.md`.

## Must

- Before work, load and follow `skills/orch-doctor/SKILL.md` read-only constraints in addition to this citation.
- Remain registered in `rules/index.yaml` with front matter mirroring `wb-create-rule` contract.

## Must Not

- Treat this pointer stub as a substitute for the skill-owned read-only constraints.

## Validation

- Confirm the skill file contains `## Read-Only Constraints (skill-owned)` with enforceable Must/Must Not.

## On Violation

Stop the doctor run, load the skill-owned constraints, and rerun doctor in read-only mode before presenting results.
