---
name: dev-systematic-debugging
description: Use when executable behavior is failing, inconsistent, or unexplained and a root-cause diagnosis is required before a durable fix is implemented.
---

# Systematic Debugging

Debug in an evidence-led sequence:

1. **Reproduce and capture evidence.** Establish the smallest reliable reproduction, expected behavior, actual behavior, and relevant logs or state.
2. **Locate the root cause.** Trace backward from the failure and identify where the incorrect state or behavior first enters the system.
3. **Compare working and broken cases.** List meaningful differences between a working and broken path, environment, input, or revision.
4. **Form one hypothesis.** State one falsifiable explanation tied to the evidence.
5. **Run a minimal experiment.** Change or observe one variable and record whether the result supports the hypothesis.
6. **Implement the root-cause fix.** Make the smallest production change that corrects the cause, not merely the visible symptom.
7. **Verify.** Rerun the reproduction and relevant regression coverage, then report only the status supported by fresh results.

Do not implement a fix before establishing the root cause. The only exception is documented containment needed to limit immediate harm; label it temporary, preserve diagnostic evidence, and continue root-cause work before calling the issue fixed.
