---
name: dev-systematic-debugging
description: Use when executable behavior is failing, inconsistent, or unexplained and a root-cause diagnosis is required before a durable fix is implemented.
---

# Systematic Debugging

Debug in an evidence-led sequence:

1. **Establish the Truth Basis.** Reconcile purpose, exact as-is evidence, applicable decision authority, expected delta, and conflict status. Stop for authority repair when they conflict.
2. **Reproduce and capture evidence.** Establish the smallest reliable reproduction, expected behavior, actual behavior, and relevant logs or state; do not let the failure itself redefine the expected behavior.
3. **Locate the root cause.** Trace backward from the failure and identify where the incorrect state or behavior first enters the system.
4. **Compare working and broken cases.** List meaningful differences between a working and broken path, environment, input, or revision.
5. **Form one hypothesis.** State one falsifiable explanation tied to the evidence.
6. **Run a minimal experiment.** Change or observe one variable and record whether the result supports the hypothesis.
7. **Implement the root-cause fix.** Make the smallest production change that corrects the cause, not merely the visible symptom; transition to TDD when the repair has a meaningful test surface.
8. **Verify.** Rerun the reproduction and relevant regression coverage, revalidate the Truth Basis and impact, and record an evidence-backed knowledge disposition.

Do not implement a fix before establishing the root cause. The only exception is documented containment needed to limit immediate harm; label it temporary, preserve diagnostic evidence, and continue root-cause work before calling the issue fixed.
