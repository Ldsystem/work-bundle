---
id: orch-handoff-required
applies_when:
  - a task, phase, or plan execution completes or is blocked
  - an executor result is created after orchestration or execution work
enforcement: must
load: conditional
requires: []
---

# Executor Result Required

## Purpose

Require one canonical factual executor result for safe continuation without granting it product-review or acceptance authority.

## Must

- Create one canonical `executor-result-v1` after task execution, including factual scope, changed paths, focused observations, blockers, task fit, repository/CodeGraph facts, delegation, and knowledge disposition.
- Validate identity, bindings, schema, canonical path, collisions, and transition before mutation; after creation perform only lightweight integrity and index checks.
- Keep executor reporting separate from independent product judgment and controller finalization.
- Treat an invalid result as blocking only continuation that requires it. Permit direct product review when exact specification/plan, frozen implementation identity, and focused observations are independently available.

## Must Not

- Do not create current orchestration handoffs, inspect or convert historical instances, infer identity from filenames, or use embedded legacy status.
- Do not put verdicts, acceptance, repair advice, final-audit conclusions, or knowledge-write authorization in executor results.

## Validation

- Confirm the canonical artifact and bindings, factual closed content, immutable bytes, and truthful partial-effect reporting.

## On Violation

- Stop the result write or dependent continuation, report the failed structural condition, and retry only with a corrected canonical executor result.
