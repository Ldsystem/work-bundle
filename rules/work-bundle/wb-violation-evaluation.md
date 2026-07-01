---
id: wb-violation-evaluation
applies_when:
  - a conflict, violation, error, failed validation, contradictory workflow behavior, user interruption, or user correction occurs during WorkBundle-guided work
  - visible task evidence suggests a WorkBundle skill, rule, script, specification, plan, handoff, workflow contract, or toolkit execution surface may have caused or contributed to the problem
  - an agent must decide whether an observed problem is work-bundle-scoped, project-scoped, mixed, or undetermined before creating violation evidence or reporting a blocker
enforcement: must
load: conditional
requires: []
---

# Violation Evaluation

## Purpose

Classify observed problems during WorkBundle-guided work early enough to preserve toolkit process evidence while keeping violation evidence storage narrow and first-observed.

## Must

- Evaluate potential WorkBundle responsibility when a conflict, violation, error, failed validation, contradictory workflow behavior, user interruption, or user correction occurs during WorkBundle-guided work.
- Use visible evidence first. If WorkBundle relatedness is already clear from a skill, rule, script, specification, plan, handoff, workflow contract, or toolkit execution surface, stop evaluation and proceed to the matching action.
- Use the active workflow chain only as a bounded first-principles aid when visible evidence does not already establish WorkBundle relatedness.
- Stop tracing as soon as visible evidence establishes that the problem is related to a WorkBundle toolkit artifact or workflow contract; do not continue searching for a deeper root cause before acting.
- Classify the observed problem as exactly one of `work-bundle-scoped`, `project-scoped`, `mixed`, or `undetermined`.
- Use `work-bundle-scoped` when visible evidence shows a WorkBundle toolkit artifact or workflow contract caused or materially contributed to the problem.
- Use `project-scoped` when the problem is limited to project business logic, project implementation, project data, or project-specific requirements with no visible WorkBundle process cause.
- Use `mixed` when both WorkBundle toolkit behavior and project-specific behavior materially contribute to the problem.
- Use `undetermined` when available evidence is insufficient to choose another classification and the classification affects authority, target scope, validation, or continuation.
- Create or update minimal violation evidence for `work-bundle-scoped` and `mixed` findings through the violation evidence workflow.
- Report `project-scoped` findings as project blockers and do not write them to the WorkBundle violation store.
- Block for resolution when an `undetermined` finding affects authority, target scope, validation, or continuation.
- Keep the evaluation result compact: trigger, short symptom, classification, visible WorkBundle-related artifact when any, trace depth, and evidence action.

## Must Not

- Do not treat the example chain `instruction -> plan -> plan skill -> source specification -> specification skill` as a mandatory fix pattern, mandatory chain-of-thought output, or exhaustive tracing path.
- Do not require full root-cause tracing after WorkBundle toolkit relatedness is visible.
- Do not create violation evidence for purely project-scoped findings.
- Do not expand evaluation into unrelated repository browsing, historical reconstruction, durable knowledge retrieval, or broad contract exploration.
- Do not store raw chat logs, private reasoning, or executor-result forbidden advice fields as the evaluation or evidence surface.
- Do not silently continue when an `undetermined` classification affects authority, target scope, validation, or continuation.

## Validation

- Confirm the trigger was a visible conflict, violation, error, failed validation, contradictory workflow behavior, user interruption, or user correction during WorkBundle-guided work.
- Confirm evaluation stopped once visible WorkBundle relatedness was established, or that the active workflow chain was used only as a bounded aid when relatedness was not already clear.
- Confirm the result uses one of `work-bundle-scoped`, `project-scoped`, `mixed`, or `undetermined`.
- Confirm `work-bundle-scoped` and `mixed` findings create or update minimal violation evidence through the evidence workflow.
- Confirm `project-scoped` findings are reported as project blockers and are not persisted in the WorkBundle violation store.
- Confirm `undetermined` findings that affect authority, target scope, validation, or continuation block for resolution.

## On Violation

Stop the unsafe continuation, repair the classification or action boundary, remove any broad root-cause tracing or forbidden evidence content, and resume only after the finding is classified and routed to violation evidence, project blocker, or resolution block as required.
