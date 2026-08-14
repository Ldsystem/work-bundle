---
name: dev-test-driven-development
description: Use when implementing new or changed executable behavior, a diagnosed bug fix, or a behavior-changing refactor with a meaningful automated test surface.
---

# Test-Driven Development

## Applicability

Use this cycle by default for new or changed executable behavior, bug fixes after diagnosis, and behavior-changing refactors when a meaningful automated test surface exists.

It is not mandatory for generated code, configuration-only changes, documentation, rules, or skills, or non-testable mechanical artifacts. A pure behavior-preserving refactor may instead establish a green baseline, proceed in small steps, and retest after each step when characterization coverage exists.

## Cycle

1. **GROUND** — reconcile the purpose, exact as-is evidence, accepted decision authority, expected delta, and conflict status. Stop for authority repair when they conflict.
2. **RED** — add the smallest test that expresses one missing behavior and a valid grounded test oracle.
3. **verify RED** — run it and confirm it fails for the intended behavioral reason, not syntax, setup, unrelated breakage, or a contradicted oracle.
4. **GREEN** — implement the smallest change that satisfies the grounded behavior.
5. **verify GREEN** — rerun the focused test and confirm it passes for the intended reason.
6. **REFACTOR** — improve names or structure without widening behavior.
7. **revalidate truth and impact** — confirm the implementation, oracle, affected paths, and accepted decisions still agree; rerun focused coverage and the broader relevant suite before completion.

If RED unexpectedly passes, repair the test or reconsider whether behavior is missing. If GREEN fails, continue with the same behavior until the focused test passes; do not hide the failure by weakening the assertion. After validation, return an evidence-backed knowledge disposition of `none`, `update`, `supersede`, or `reclassify`; this does not authorize a knowledge write.
