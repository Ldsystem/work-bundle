---
id: ks-persistence-gate
applies_when:
  - knowledge write may occur
enforcement: must
load: conditional
requires: []
---

# Ks Persistence Gate

## Purpose

- Define the mandatory pre-write gate for every keep-summarizing persistence action.
- Block writes until project, path, safety, and note metadata checks all pass.

## Must

- Complete all eight workflow checks before any write:
  1. Project is resolved to `.work-bundle/knowledge/` or an explicitly selected external legacy source for migration or read-only intake.
  2. The selected directive allows writing.
  3. Target path is under `notes/<lifecycle-stage>/<leaf-perspective>/`, `open-questions/<lifecycle-stage>/<leaf-perspective>/`, or `context-packs/`.
  4. The perspective is a lifecycle-aware leaf path covered by `ks-perspective-routing`.
  5. The content passes `ks-sensitivity-filter`.
  6. Lifecycle stage, status, source type, and evidence are valid and justified.
  7. Existing related notes were checked for duplicate or conflicting knowledge.
  8. Required front matter is present before completion.
- Treat `ks-structural-value` as an additional hard precondition before the gate is considered satisfied for durable knowledge writes.
- If any check fails, do not write.

## Must Not

- Do not guess a missing project root, directive, lifecycle stage, status, source type, evidence set, or target path.
- Do not bypass duplicate or conflict review.
- Do not continue to a write after any failed gate check.
- Do not replace the required failure response with silent refusal or partial persistence.

## Validation

- Confirm checks 1 through 8 were completed explicitly before a durable write proceeds.
- Confirm sensitivity review is handled through `ks-sensitivity-filter` and structural-value review is handled through `ks-structural-value` instead of restating those full lists here.
- On any failed check, return `Waiting for your direction` and include the failed check plus concrete next options.

## On Violation

- Stop the write immediately.
- Return `Waiting for your direction`, identify the failed check, and present the minimum concrete next actions needed to pass the gate.
