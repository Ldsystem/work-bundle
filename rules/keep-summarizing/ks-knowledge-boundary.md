---
id: ks-knowledge-boundary
applies_when:
  - knowledge access or write is requested
enforcement: must
load: conditional
requires: []
---

# Ks Knowledge Boundary

## Purpose

- Define the durable knowledge boundary for keep-summarizing work.
- Keep durable knowledge under the managed knowledge root and keep orchestration artifacts under orchestration ownership.

## Must

- Treat `.work-bundle/knowledge/` as the default durable source of truth for one managed project.
- Read a legacy knowledge root only when the user or task explicitly selects it for migration or read-only intake.
- Keep durable note writes under `.work-bundle/knowledge/notes/`, `.work-bundle/knowledge/open-questions/`, or `.work-bundle/knowledge/context-packs/` only when the active directive allows persistence.
- Route specification, plan, task, handoff, and reader-facing artifact work to the matching `orch-*` rule or skill instead of treating that work as durable knowledge authoring.
- Treat `.work-bundle/orchestration/handoff/` as orchestration output, not durable knowledge.

## Must Not

- Do not write orchestration artifacts as knowledge.
- Do not treat `.work-bundle/orchestration/` as a durable knowledge root.
- Do not treat a legacy knowledge root as writable by default.
- Do not answer an orchestration-document request by storing the document as a knowledge note.

## Validation

- Confirm the selected durable root is `.work-bundle/knowledge/` unless an external legacy root was explicitly selected for migration or read-only intake.
- Confirm every write target stays under the allowed knowledge subtrees and does not point into `.work-bundle/orchestration/`.
- Confirm orchestration requests are redirected to the relevant `orch-*` workflow before any durable knowledge write begins.

## On Violation

- Stop the write or retrieval step.
- Report which boundary was crossed, name the correct root or owning workflow, and make the minimal routing correction before continuing.
