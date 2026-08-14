---
name: dev-code-review
description: Use for an independent review of a completed implementation task before acceptance, integration, or downstream reliance on its result.
---

# Code Review

Review against the accepted task and the exact tree or commit identity. Independence means the reviewer did not author the change; if that is false, disclose it and do not present the review as independent.

Check:

1. **grounded intent** — purpose, as-is source evidence, accepted decision authority, expected delta, and conflict status agree.
2. **task fit** — the change implements the grounded scope and avoids unrelated behavior.
3. **rules and methodology** — applicable repository rules and required development methods were followed.
4. **correctness and edge cases** — normal, boundary, failure, compatibility, and lifecycle paths behave correctly.
5. **test oracle and validation evidence** — the oracle follows grounded intent, RED failed for the intended reason when TDD applied, and fresh checks support the claim.
6. **knowledge disposition** — `none`, `update`, `supersede`, or `reclassify` is supported by task-local evidence and does not instruct persistence.
7. **unnecessary complexity** — no speculative abstraction, redundant path, or avoidable change radius was introduced.

Return exactly this compact shape; omit no keys:

```yaml
task_review:
  reviewer_independent: true | false
  verdict: accept | repair | blocked
  reviewed_head: <commit-or-tree-identity>
  findings:
    - severity: blocking | advisory
      scope: specification | correctness | quality | validation | rule
      finding: <compact evidence-backed text>
```

Use `findings: []` when there are no findings. Green tests do not override a contradiction in intent, decision authority, or test oracle. Choose `repair` for an actionable defect and `blocked` when authoritative scope, source identity, conflict resolution, or capable evidence is unavailable.
