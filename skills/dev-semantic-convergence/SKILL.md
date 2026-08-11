---
name: dev-semantic-convergence
description: Use when drafting or repairing specifications, plans, rules, skills, contracts, reviews, or other semantic artifacts that must agree across caller-defined views before they can be accepted.
---

# Semantic Convergence

Apply this loop only to semantic artifacts. The caller owns the artifact set, the caller-defined lenses, the round limit, and any authority hierarchy.

## Loop

1. Mark the current artifact set `DRAFT`.
2. Render a `VIEW` through each caller-defined lens. A lens may expose requirements, interfaces, lifecycle states, evidence, ownership, or another declared concern.
3. Compare the views and identify only concrete drift, gap, contradiction, or unsupported claim.
4. In the authoritative draft, repair only the demonstrated defects. Preserve unrelated meaning and structure.
5. Render every affected `VIEW` again.
6. Stop as `converged` when a complete round is unchanged. Stop as `blocker` when authority is missing, views cannot be reconciled, or the caller's round limit is reached. Do not claim convergence merely because edits became small.

## Result

Return a compact result:

```yaml
semantic_loop:
  result: converged | blocker
  rounds: <positive-integer>
  repaired:
    - <artifact-and-defect>
```

Use an empty `repaired: []` when no defect required repair. For a blocker, append only the compact unresolved reason needed by the caller.
