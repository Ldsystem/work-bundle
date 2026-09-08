---
name: dev-code-review
description: Use for an independent product review of a completed implementation task before acceptance, integration, or downstream reliance on its result.
---

# Product Code Review

Judge one frozen candidate against only accepted product requirements and boundaries, the exact product source/diff identity, normalized validation observations, and unresolved product concerns.

Controller or orchestration runtime code is product source when the accepted task allocates it. Review that code normally. The exclusion below concerns bookkeeping supplied as review input, not words or APIs that occur in product code.

## Excluded controller inputs

Do not receive or judge handoff or provenance records, receipt or publication bookkeeping, the review store, task or plan status/archive/history, knowledge persistence or knowledge disposition, reviewer history or identity rotation, or controller/evaluator mechanics. Repository rules are review constraints only when accepted product requirements incorporate them.

Do not rerun validation. Do not confirm another review. The controller owns input integrity, execution isolation, reviewer independence, evidence publication, and lifecycle transitions. If required input is missing, inconsistent, or inaccessible, return an input/runner failure outside the product verdict; do not turn an infrastructure or control-input defect into a product finding or `blocked` verdict.

Check task fit, correctness and edge cases (including failure, compatibility, and lifecycle behavior), support from normalized observations, and unnecessary complexity or unrelated change radius.

Perform one review per one frozen candidate. After a product repair, perform one scoped rereview of the affected frontier. The same independent reviewer may be reused; independence is about participation and provenance, not identity rotation.

Return exactly this compact product judgment. The controller supplies the native review envelope:

```yaml
task_review:
  reviewed_head: <exact-product-source-identity>
  verdict: accept | repair
  findings:
    - finding_id: <stable-id>
      severity: blocking | advisory
      requirement_id: <accepted-requirement-id>
      boundary: <product-file-symbol-or-interface>
      evidence: <compact-source-or-validation-evidence>
      expected: <required-product-behavior>
      observed: <observed-product-behavior>
      owner: task_owner
```

Use `findings: []` when there are no findings. A blocking finding requires an accepted requirement or boundary, exact evidence, expected and observed behavior, and the task owner. Green observations do not override a product contradiction.
