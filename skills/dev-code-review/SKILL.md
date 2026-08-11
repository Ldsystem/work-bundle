---
name: dev-code-review
description: Use for an independent review of a completed implementation task before acceptance, integration, or downstream reliance on its result.
---

# Code Review

Review against the accepted task and the exact tree or commit identity. Independence means the reviewer did not author the change; if that is false, disclose it and do not present the review as independent.

Check:

1. **task fit** — the change implements the requested scope and avoids unrelated behavior.
2. **rules and methodology** — applicable repository rules and required development methods were followed.
3. **correctness and edge cases** — normal, boundary, failure, compatibility, and lifecycle paths behave correctly.
4. **unnecessary complexity** — no speculative abstraction, redundant path, or avoidable change radius was introduced.
5. **validation evidence** — fresh checks are capable of supporting the claimed behavior and scope.

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

Use `findings: []` when there are no findings. Choose `repair` for an actionable defect and `blocked` when authoritative scope, source identity, or capable evidence is unavailable.
