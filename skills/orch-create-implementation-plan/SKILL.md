---
name: orch-create-implementation-plan
description: 'Create executable WorkBundle plans, phases, and tasks from a verified specification when implementation needs dependency, scope, validation, methodology, or delegation structure.'
---

# orch-create-implementation-plan

## Entry gate

Plan only from an active specification whose `Quality gate: verified`, compact `semantic_loop.result: converged`, blocking questions, stable source IDs, Knowledge Base Update disposition, and repository metadata evidence are coherent. Repair the specification instead of inventing missing requirements or decisions.

## Planning workflow

1. Use the source specification and bounded task-relevant repository evidence. Treat source-spec impact-radius evidence as authoritative scope; add upstream/downstream or validation/test scope only when current evidence proves it.
2. Prefer the fewest phases and tasks that preserve safe execution, validation ownership, and review independence.
3. Give every task exact source IDs, file and symbol scope, interfaces, dependencies, steps, completion evidence, methodology, allocated rules/skills, provider-neutral executor profile, and acceptance-review requirement.
4. Carry the specification's execution-workspace isolation, hydration profile, and cleanup policy into task and executor context.
5. Use a common contract group before safe parallel work. Contract-decoupled participants depend on the common contract group and accepted prior handoffs, not sibling in-progress implementation output. Create explicit barrier metadata with barrier ID, readiness evidence, and convergence owner. Cross-branch or joint validation belongs to a post-barrier convergence task.
6. Require a compact `executor-result-v1` handoff and task review before a review-required task can complete.

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

Durable task artifacts remain normalized and cite `source_ids`. Set `context_mode: compiled-brief`; the ephemeral compiler may duplicate resolved values for a bounded executor. Never put provider or model-vendor names in durable contracts.

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
```

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

Follow `orch-orchestration-boundary`. Do not read durable knowledge directly during downstream execution. Role-context is deprecated; do not invoke it from orch skills.
