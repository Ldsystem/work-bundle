---
name: dev-test-driven-development
description: Use when implementing new or changed executable behavior, a diagnosed bug fix, or a behavior-changing refactor with a meaningful automated test surface.
---

# Test-Driven Development

## Applicability

Use this cycle by default for new or changed executable behavior, bug fixes after diagnosis, and behavior-changing refactors when a meaningful automated test surface exists.

It is not mandatory for generated code, configuration-only changes, documentation, rules, or skills, or non-testable mechanical artifacts. A pure behavior-preserving refactor may instead establish a green baseline, proceed in small steps, and retest after each step when characterization coverage exists.

## Cycle

1. **RED** — add the smallest test that expresses one missing behavior.
2. **verify RED** — run it and confirm it fails for the intended behavioral reason, not syntax, setup, or unrelated breakage.
3. **GREEN** — implement the smallest change that satisfies the behavior.
4. **verify GREEN** — rerun the focused test and confirm it passes.
5. **REFACTOR** — improve names or structure without widening behavior.
6. **stay green** — rerun focused coverage after refactoring, then run the broader relevant suite before claiming completion.

If RED unexpectedly passes, repair the test or reconsider whether behavior is missing. If GREEN fails, continue with the same behavior until the focused test passes; do not hide the failure by weakening the assertion.
