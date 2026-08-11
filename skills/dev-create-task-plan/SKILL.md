---
name: dev-create-task-plan
description: Use when a bounded, mechanical code change needs a lightweight executable task plan and none of the escalation conditions require full orchestration planning.
---

# Create Task Plan

Create a bounded mechanical plan only when scope, behavior, and implementation direction are already settled. Escalate to the full orchestration workflow for an architecture, API, data-model, or workflow decision; wide impact radius; multiple repositories; migration or deployment; durable knowledge work; or parallel barriers.

Write the plan under `.work-bundle/runtime/dev-plans/` with a stable task-oriented filename. Populate every field with concrete paths, symbols, commands, and expected results.

Choose exactly one initial Method value: `tdd`, `systematic-debugging`, `direct`, or `loop-coding`. Bug work starts with `systematic-debugging` until diagnosis; a testable repair then transitions to `tdd`. When `dev-test-driven-development` applies, Steps must explicitly preserve this order: RED, verify RED, GREEN, verify GREEN, REFACTOR, rerun and stay green.

Use exactly this structure:

```markdown
# Mechanical Execution Plan

## Goal
[One bounded outcome.]

## Method
[tdd | systematic-debugging | direct | loop-coding]

## Capability
[Required tools and permissions.]

## Files
- Read: [paths]
- Modify: [paths]
- Test: [paths]

## Interfaces
- Consumes: [inputs/contracts]
- Produces: [outputs/contracts]

## Steps
1. Baseline — [command and expected result]
2. Change — [file/symbol and concrete code or pseudocode]
3. Verify — [command and expected result]
4. If verification fails — [bounded diagnosis or stop condition]
5. Commit if permitted — [scope and message, or not permitted]

## Completion evidence
[Fresh evidence required for the exact completion claim.]
```

Do not use this lightweight artifact to conceal unresolved design choices or broaden the authorized change.
