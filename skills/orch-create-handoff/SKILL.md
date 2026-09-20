---
name: orch-create-handoff
description: Create a canonical factual executor result for safe WorkBundle continuation without issuing product acceptance.
---

# Create an Executor Result

Use this skill after task execution or when a current executor result must be repaired. The current machine boundary is `executor-result-v1`; do not create orchestration handoffs or convert historical artifacts.

## Workflow

1. Confirm the exact plan/task bindings, identity, lifecycle operation, and canonical catalog location.
2. Summarize only factual implemented scope, changed paths, validation observations, unresolved product blockers, task fit, repository/CodeGraph observations, delegation provenance, and task-local knowledge disposition.
3. Validate the full semantic input, bindings, identity, canonical path, and requested transition before mutation.
4. Create or repair the active YAML artifact atomically at the same canonical identity. Allocate a new identity only for a genuinely distinct executor result; a transitioned result is not rewritten. Treat the derived index as a regenerable projection.
5. After the write, perform only lightweight integrity checks. If index rebuild fails after the artifact write, report the partial effect truthfully.

A malformed or missing executor result blocks only continuation that requires it. An independent reviewer may still judge an exact reviewable product candidate from the verified specification/plan, frozen implementation identity, and focused observations.

## Self-check

- [ ] The artifact is at the catalog-selected path and bound to the exact plan/task.
- [ ] The content is factual and contains no verdict, acceptance, final-audit, repair-advice, or knowledge-write fields.
- [ ] Necessary structural validation completed before mutation; active repair retained the canonical identity and did not create a revision copy.
- [ ] Post-write work was limited to integrity and index projection checks.
- [ ] Any partial effect or separate supporting-state defect is reported without changing product meaning.
