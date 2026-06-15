---
id: ks-perspective-routing
applies_when:
  - note path or perspective is selected
enforcement: must
load: conditional
requires: []
---

# Ks Perspective Routing

## Purpose

- Define the lifecycle-aware leaf paths that may own durable knowledge.
- Keep each durable fact in one canonical, most-specific perspective instead of broad or duplicate placement.

## Must

- Use only the most specific lifecycle-aware leaf path when selecting `notes/<lifecycle-stage>/<leaf-perspective>/` or `open-questions/<lifecycle-stage>/<leaf-perspective>/`.
- Use these allowed lifecycle-aware leaf paths:
  - `tender`: `background`, `requirements`, `constraints`, `deliverables`, `glossary`
  - `investigation`: `scope-of-work`, `user-portrait`, `business-boundary`, `process-flow`, `performance-requirement`, `integration-landscape`, `risks`, `constraints`
  - `customer-design`: `business-boundary`, `process-flow`, `functional-modules`, `user-flow`, `ui-prototype`, `acceptance-criteria`, `non-goals`
  - `bidding`: `committed-scope`, `exclusions`, `deliverables`, `milestones`, `assumptions`, `risks`
  - `development-design/architecture`: `system-boundary`, `component-boundary`, `dependency-direction`, `source-of-truth`, `decisions`, `patterns`
  - `development-design/workflow`: `process-flow`, `data-flow`, `state-lifecycle`, `control-flow`
  - `development-design/data`: `data-model`, `schema`, `identifiers`, `relationships`, `lineage`, `migration`
  - `development-design/interfaces`: `api-contract`, `event-contract`, `file-contract`, `error-contract`, `compatibility`
  - `development-design/implementation`: `backend`, `frontend`, `database`, `cache`, `async-messaging`
  - `development-design/quality`: `requirements`, `validation`, `testing-strategy`, `edge-cases`, `performance`, `observability`
  - `implementation`: `implemented-features`, `reusable-functions`, `module-structure`, `code-structure`, `coding-rules`, `tests`, `known-limitations`, `implementation-decisions`
  - `deployment`: `topology`, `configuration`, `packaging`, `migration`, `backup-restore`, `resource-limits`, `rollout-rollback`, `startup-shutdown`, `security-permission`
  - `go-live-delivery`: `acceptance-result`, `delivery-scope`, `handover`, `training`, `final-exclusions`, `support-boundary`, `production-cutover`
  - `operation`: `runtime-observation`, `troubleshooting`, `incidents`, `performance`, `maintenance`, `optimization`, `security-audit`
- Keep one canonical note for each durable fact in the most specific owning perspective.
- When the same durable fact appears in multiple notes:
  - choose the canonical perspective that best owns the fact;
  - update or propose deprecating duplicate full-body notes;
  - keep only a short cross-perspective stub when a secondary perspective needs discoverability;
  - make the stub link to the canonical note and avoid restating the full rule;
  - ask before changing or deprecating conflicting `current` notes.
- Keep stable domain rules, business semantics, validation rules, lifecycle rules, source-of-truth rules, and process or data-flow rules in the matching domain perspective rather than leaving them only in implementation-shaped notes.

## Must Not

- Do not store durable facts in broad container nodes.
- Do not pick a non-leaf perspective when a more specific leaf exists.
- Do not maintain duplicate full-body `current` notes across perspectives.
- Do not use implementation or interface notes as the only home for stable domain or workflow rules they do not own.

## Validation

- Confirm the selected path is a lifecycle-aware leaf from this rule before a note is created or moved.
- Confirm the chosen perspective is the most specific owner for the fact being recorded.
- Confirm duplicate or conflicting notes were checked and canonical ownership was chosen explicitly.

## On Violation

- Stop placement or relocation.
- Report the incorrect path, name the correct owning leaf perspective, and make the minimal routing change before continuing.
