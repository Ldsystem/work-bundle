---
name: orch-create-handoff
description: Create or repair a current factual executor result after task execution for WorkBundle continuation. Excludes product acceptance and historical handoff conversion.
---

# Create an Executor Result

Use this skill after task execution or when a current executor result must be repaired. The current machine boundary is `executor-result-v2`; do not create orchestration handoffs or convert historical artifacts.

## Workflow

1. Confirm the exact plan/task bindings, identity, lifecycle operation, and canonical catalog location.
2. Summarize only factual implemented scope, changed paths, validation observations, unresolved product blockers, task fit, repository/CodeGraph observations, delegation provenance, and task-local knowledge disposition.
   For the designated phase delivery task, materialize the canonical temporary bundle first. Only a published payload may appear in `phase_handoff`: exact bundle/snapshot/manifest and bridge identities, reproducible entrypoint instructions, required bridge observations, the complete `--all` report, and limitations. Failed observations remain factual; they do not authorize acceptance. Ordinary tasks omit this payload.
3. Validate the full semantic input, bindings, identity, canonical path, and requested transition before mutation.
4. Supply semantic input to `scripts/orch.py write-executor-result` to create or repair the active YAML artifact atomically at the same canonical identity. Allocate a new identity only for a genuinely distinct executor result; a transitioned result is not rewritten. Treat the derived index as a regenerable projection.
5. Apply `orch-artifact-authoring`: do not directly create or edit canonical YAML/Markdown under `.work-bundle/orchestration/`, including bootstrap repair. The writer handles malformed-active repair; target-affecting conflicts still reject before mutation.
6. After the write, perform only lightweight integrity checks. Report `write_effect: applied` with `index_effect: stale` and unrelated sibling diagnostics truthfully; repair each sibling through its own family writer, then use the existing index command.

A malformed or missing executor result blocks only continuation that requires it. An independent reviewer may still judge an exact reviewable product candidate from the verified specification/plan, frozen implementation identity, and focused observations.

## Self-check

- [ ] Actual creation/active repair used `scripts/orch.py write-executor-result`; no direct canonical or bootstrap edit occurred.
- [ ] The artifact is at the catalog-selected path and bound to the exact plan/task.
- [ ] The content is factual and contains no verdict, acceptance, final-audit, repair-advice, or knowledge-write fields.
- [ ] Necessary structural validation completed before mutation; active repair retained the canonical identity and did not create a revision copy.
- [ ] Post-write work was limited to integrity and index projection checks.
- [ ] Any partial effect or separate supporting-state defect is reported without changing product meaning.
