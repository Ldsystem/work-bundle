---
name: orch-doctor
description: 'Diagnose current orchestration contracts, skills, catalog, and public commands read-only. Reports structural findings and agent-assessed instruction conflicts; excludes applying repairs.'
---

# Orchestration Doctor

Diagnose the maintained orchestration contracts and instruction boundaries read-only. Report concrete findings and repair owners without applying fixes.

## Workflow

1. Run `python3 scripts/orch.py doctor` through the current public dispatcher. It checks maintained catalog policies, current/retired command registration, required contract references, self-check presence, and evaluation fixture shape. A structural failure is a bounded observation, not a product verdict.
2. Inspect only the affected `skills/orch-*/SKILL.md`, `rules/orchestration/`, `references/assets/orchestration/workflow.md`, referenced contracts, and existing orchestration evaluation cases needed to explain the finding. Installation symlink/front-matter checks may use `python3 bin/work-bundle-skill validate` when installation is in diagnosis scope.
3. As an agent, assess the actual instruction purpose and observable positive, negative, and adjacent request cases. Scripts check fields, references, and fixture structure; they do not select applicability, evaluate meaning, or declare semantic coverage.
4. Report the exact conflicting instruction/contract and first repair owner. Do not invoke mutation, artifact writers, initialization, installation, or knowledge retrieval as part of doctor.

## Current boundary checks

- Specification, planning, execution, factual results, advisory implementation review, controller acceptance, and final workflow audit retain distinct roles.
- Registered artifact creation and malformed-active repair follow `orch-artifact-authoring`: semantic payload to the canonical family writer or focused amendment. Unrelated bad siblings may leave a projection stale without becoming a product verdict or direct-edit authorization.
- Execution consumes the accepted task packet, bound repository/write scope, carried Truth Basis/rule obligations, and accepted predecessors. The controller owns scope, worker routing, repair, continuation, and acceptance.
- Task review is required only when the task's `acceptance_review.required` is true; an omitted optional review is not a structural defect. Integrated implementation review and final audit keep their allocated scopes.
- Knowledge-using authoring/review uses the approved gateway; accepted execution workers and execution-completion results consume carried authority without retrieval.
- Current CodeGraph policy distinguishes indexed source work from `no-index`/`sync-failed` fallback and non-code instruction work.
- Executor results contain factual scope/observations and no product verdict, repair advice, or knowledge-write authority. Designated delivery tasks alone publish phase handoffs; accepted snapshots surface asynchronously.
- Delivery/snapshot observation reuse, cleanup, finalization, and historical immutability retain their existing identity-bound procedures. Read-only diagnosis never authorizes those effects.

## Output

```text
Doctor result: passed|issues-found|blocked
Structural observations:
- <actual command/check result>
Agent instruction assessment:
- <bounded finding or no demonstrated conflict>
Recommended repairs:
- <exact owner and action or none>
Files changed: none
```

Report an unavailable command as unavailable; do not invent a pass or impose an obsolete `dev-rules-doctor`/`$DEV_RULES_HOME` prerequisite.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`

Central `AGENTS.md` owns indexed rule discovery and exact-context reuse; consume accepted worker obligations where applicable.

## Self-check

- [ ] Actual structural results and agent semantic assessment are distinguished.
- [ ] Diagnosis stayed in the requested instruction/contract scope and made no file changes.
- [ ] Any review requirement follows current task allocation; scripts and reviewer advice issue no acceptance decision.
- [ ] Findings cite the first owning instruction or contract, with no obsolete prerequisite or added workflow gate.
