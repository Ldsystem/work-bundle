---
name: orch-create-implementation-plan
description: 'Create executable WorkBundle plans, phases, and tasks from a verified specification when implementation needs dependency, scope, validation, methodology, or delegation structure.'
---

# orch-create-implementation-plan

## Entry gate

Plan only from a verified active specification with converged semantics, resolved blockers, stable source IDs, explicit knowledge disposition, and coherent repository evidence. Repair missing authority.

## Planning workflow

1. Use the specification and bounded repository evidence. Add upstream/downstream or validation scope only when current evidence proves it.
2. Use the minimum orchestration overhead that preserves Truth Basis continuity, independently falsifiable and testable increments, short evidence loops, exact dependencies, disjoint write scopes, validation ownership, bounded failure radius, and review boundaries. Do not split one mechanical increment when it already satisfies those constraints.
3. Give every task exact source IDs, a five-field Truth Basis, scope, interfaces, dependencies, steps, evidence, methodology, allocated rules/skills, executor profile, and review requirement.
4. Carry execution-workspace isolation, hydration, and cleanup policy into task and executor context.
5. Use a common contract group before safe parallel work. Contract-decoupled participants depend on the common contract group and accepted prior handoffs, not sibling in-progress implementation output. Create explicit barrier metadata with barrier ID, readiness evidence, and convergence owner. Cross-branch or joint validation belongs to a post-barrier convergence task.
6. Require a compact `executor-result-v1` handoff and task review before a review-required task can complete.
7. When a consequential simplification or compatibility assumption exists, make the earliest ordinary task cheaply falsify it before broad edits. Do not add a risk score, checkpoint phase, or parallel lifecycle.

## Methodology allocation

```text
semantic artifact              -> dev-semantic-convergence
unexpected behavior            -> dev-systematic-debugging
diagnosed testable repair       -> dev-test-driven-development
new/changed testable behavior   -> dev-test-driven-development
behavior-preserving refactor    -> loop-coding with green characterization baseline
configuration/generated/docs   -> direct with deterministic checks
task acceptance                 -> dev-code-review
```

## Executor profile

- `mechanical`: one or two files, exact contracts and commands, little judgment.
- `standard`: multi-file coordination, pattern matching, debugging, or integration.
- `judgment`: architecture, concurrency, ambiguous tradeoffs, or high-risk review.

Durable tasks cite `source_ids` and set `context_mode: compiled-brief`; the compiler may duplicate resolved values. Keep provider names out of durable contracts.

## Required task concepts

```yaml
methodology:
  primary: tdd | systematic-debugging | direct | loop-coding
  required_skills: []
executor_profile:
  capability: mechanical | standard | judgment
  context_mode: compiled-brief
  review_capability: standard | judgment
  escalation:
    after_failed_repairs: 2
    next_capability: standard | judgment
acceptance_review:
  required: true | false
  reviewer_independent: false
  verdict: pending | accept | repair | blocked
  reviewed_head: ""
  findings: []
truth_basis:
  purpose: <bounded outcome>
  as_is_evidence: []
  decision_authority: [none-relevant | <AUTH-NNN alias allocated from verified specification source_knowledge>]
  expected_delta: []
  conflict_status: clear | escalate
```

The compiler resolves each allocated `AUTH-NNN` alias to `AUTH-NNN: <carried constraint>` from verified specification `source_knowledge` without exposing knowledge paths.

## Semantic convergence

Use `dev-semantic-convergence` with these lenses:

- source-ID coverage;
- dependencies, task boundaries, and write scopes;
- validation ownership;
- rule, skill, and methodology allocation;
- parallel barrier and convergence safety;
- executor-context completeness.

Repair generated drift in the same turn and record compact `semantic_loop` result, round count, and repaired defects. If a source requirement or decision is missing, stop for specification repair.

## Runtime Rules

- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`
- `orch-open-questions`: `rules/orchestration/orch-open-questions.md`
- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`

Central `AGENTS.md` owns rule discovery and loading. Load the runtime rules above when their indexed conditions apply.

## Boundary

Follow `orch-orchestration-boundary`. Do not read durable knowledge directly during downstream execution.
