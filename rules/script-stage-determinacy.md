---
id: script-stage-determinacy
applies_when:
  - an agent designs, creates, or refactors a WorkBundle script or reusable workspace utility
  - an agent delegates a lifecycle-stage conclusion, gate, or transition to deterministic automation
enforcement: must
load: conditional
requires: []
---

# Script Stage Determinacy

## Purpose

Keep scripts authoritative for determinate mechanics without turning incomplete current-stage evidence into semantic or lifecycle judgment.

## Must

- Before automation selection, name the current lifecycle stage, current named obligations, available current facts, supplied policy, and exact conclusion, gate, or transition proposed for automation.
- Automate that conclusion only when the current facts and supplied policy determine it at the current stage.
- When the conclusion is not determined, return bounded observations and leave interpretation, sufficiency, remediation, qualification, and acceptance with the responsible agent or controller.
- Treat structural facts and reviewer advice as inputs to the responsible semantic decision, never as substitutes for that decision.
- Keep release-only and later-stage burdens out of a current development loop unless a current named obligation requires them.

## Must Not

- Do not introduce a mandatory score, taxonomy, keyword proxy, or other heuristic to manufacture determinacy.
- Do not add a new schema field, semantic script gate, or new review lifecycle merely to encode an agent-owned conclusion.
- Do not treat a passing structural check, reviewer recommendation, or missing future-stage artifact as an automatic semantic verdict.

## Validation

- Confirm the stage, current obligations, facts, policy source, and requested conclusion are explicit before deciding what the script owns.
- Confirm every automated conclusion follows mechanically from current inputs and supplied policy.
- Confirm indeterminate cases report actionable bounded observations without issuing qualification, remediation, acceptance, or lifecycle judgment.

## On Violation

Stop delegating the conclusion to the script, narrow its output to bounded observations, and return the semantic decision to the responsible agent or controller.
