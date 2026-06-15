---
id: orch-execute-plan
applies_when:
  - user invokes orch-execute-plan or the execute-plan directive
  - execute-plan resolves or begins an executable task or scheduler wave
enforcement: must
load: conditional
requires: []
---

# Execute Plan Execution Boundary

## Purpose

Enforcement pointer for `orch-execute-plan`. Full Must/Must Not live in `skills/orch-execute-plan/SKILL.md`.

## Must

- Before work, load and follow `skills/orch-execute-plan/SKILL.md` execution constraints in addition to this citation.
- Remain registered in `rules/index.yaml` with front matter mirroring `wb-create-rule` contract.

## Must Not

- Treat this pointer stub as a substitute for the skill-owned execution constraints.

## Validation

- Confirm the skill file contains `## Execution Constraints (skill-owned)` with enforceable Must/Must Not.

## On Violation

Stop execution, load the skill-owned constraints, and restart under `execute-plan` before continuing.
