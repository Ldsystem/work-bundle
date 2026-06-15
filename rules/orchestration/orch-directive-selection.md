---
id: orch-directive-selection
applies_when:
  - user invokes any orch-* skill or orchestration directive
  - an orchestration request starts without a declared primary directive
enforcement: must
load: conditional
requires: []
---

# Orchestration Directive Selection

## Purpose

Ensure every orchestration request runs under exactly one primary directive or an explicitly declared multi-step sequence. The orchestrator owns specifications, plans, documents, and handoffs as derived orchestration artifacts; it does not own durable project knowledge.

## Must

- Select one primary directive before substantive orchestration work begins.
- When work spans multiple directives, declare the ordered multi-step sequence explicitly before proceeding.
- Match the selected directive to the user's intent using the orchestration directive set: `create-specification`, `create-implementation-plan`, `execute-plan`, `create-handoff`, `review-plan`, `create-document`, and `doctor`.
- Keep directive responsibilities distinct: document authoring, specification authoring, planning, execution, review, handoff recording, and read-only diagnosis must not be blended in one undifferentiated pass.
- Stop and re-select when the active work no longer matches the declared directive.

## Must Not

- Blend orchestration modes without first selecting or declaring the directive sequence.
- Start artifact creation, execution, review, or diagnosis without naming the governing directive.
- Treat durable knowledge maintenance as an orchestration directive; route durable writes to approved `ks-*` owners.
- Switch directives silently mid-task without declaring the new primary directive or sequence step.

## Validation

- Confirm the active directive is named before loading directive-specific contracts or writing orchestration artifacts.
- Confirm multi-step work lists each directive in execution order.
- Confirm the selected directive matches the artifact type being created or the operation being performed.

## On Violation

Stop orchestration work, name the correct primary directive or multi-step sequence, and restart under that selection before continuing.
