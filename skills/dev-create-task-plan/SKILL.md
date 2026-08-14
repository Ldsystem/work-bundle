---
name: dev-create-task-plan
description: Use when a bounded, mechanical code change needs a lightweight executable task plan and none of the escalation conditions require full orchestration planning.
---

# Create Task Plan

Create a bounded mechanical plan only when scope, behavior, and implementation direction are already settled. Escalate to the full orchestration workflow for an architecture, API, data-model, or workflow decision; wide impact radius; multiple repositories; migration or deployment; durable knowledge work; or parallel barriers.

Before choosing a method, establish a compact Truth Basis: purpose, exact as-is evidence, applicable accepted decision authority, expected delta, and conflict status. Use `clear` only when those inputs agree. If conflict status is `escalate`, stop and route to clarification, specification repair, or full orchestration; do not use a lightweight plan to invent authority.

After repository preflight and exact source grounding, invoke `ks-what-is-helpful` once in bounded gateway mode with neutral task anchors. Carry materially relevant accepted authority into the Truth Basis, or record evidence-backed `none relevant`. Candidate, background, blocked, opposing, or constraining results may explain a conflict but cannot become decision authority. A material conflict sets `conflict_status: escalate`; the gateway does not create heavy artifacts or authorize knowledge writes.

Write the plan under `.work-bundle/runtime/dev-plans/` with a stable task-oriented filename. Populate every field with concrete paths, symbols, commands, and expected results.

Choose exactly one initial Method value: `tdd`, `systematic-debugging`, `direct`, or `loop-coding`. Bug work starts with `systematic-debugging` until diagnosis; a testable repair then transitions to `tdd`. When `dev-test-driven-development` applies, Steps must explicitly preserve this order: GROUND, RED, verify RED, GREEN, verify GREEN, REFACTOR, revalidate truth and impact.

Use exactly this structure:

```markdown
# Mechanical Execution Plan

## Goal
[One bounded outcome.]

## Truth Basis
- Purpose: [why this result is needed]
- As-is evidence: [exact source, test, or harness evidence]
- Decision authority: [accepted authority or evidence-backed `none relevant`]
- Expected delta: [observable post-change behavior]
- Conflict status: clear | escalate

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

## Knowledge disposition
- Action: none | update | supersede | reclassify
- Reason: [post-validation evidence; no knowledge write instruction]
```

The plan is disposable runtime state, not durable knowledge. Record the disposition after validation; use `none` when no stable authority changed. Do not use this lightweight artifact to conceal unresolved design choices, broaden the authorized change, or create heavy specification/task/review artifacts.

## Lightweight completion owner

The agent owning this lightweight plan is the lightweight completion owner. After validation it evaluates the final disposition:

- `none`: record an evidence-backed no-write result and complete without invoking a writer.
- `update`, `supersede`, or `reclassify`: invoke the approved keep-summarizing lifecycle, then validate its returned structural-value decision, written or updated paths or no-write rationale, index status, and blockers before completion.

This owner is distinct from final orchestration review, which owns durable closure only for the heavy path. Lightweight completion never creates an orchestration review artifact.
