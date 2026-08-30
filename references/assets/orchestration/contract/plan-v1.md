---
id: plan-YYYYMMDD-001
goal: [Concise title describing the implementation plan goal]
purpose: [upgrade|refactor|feature|data|infrastructure|process|architecture|design]
component: [target component/module/system]
version: 1
date_created: YYYY-MM-DD
last_updated: YYYY-MM-DD
owner: [team/individual/agent]
status: Planned
tags:
  - [feature|upgrade|chore|architecture|migration|bug|data|process]
source_spec:
  - .work-bundle/orchestration/spec/active/...
source_knowledge:
  - carried by source specification
phase_index:
  - id: phase-001
    name: [Phase Name]
    path: .work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug].md
    status: Planned
    depends_on: []
    parallelizable: true
allocated_rules:
  - id: [rule-id]
    source: AGENTS.md|work-bundle-toolkit|work-bundle-global|work-bundle-project|builtin|plugin|other
    path: [file path when file-backed, otherwise source label]
    applies_when: [observable plan-wide condition]
    load_timing: before_planning|before_task_work|before_validation
    enforcement: must|should
allocated_skills:
  - name: [skill-name]
    source: work-bundle|agents-skills|codex-skills|builtin|plugin|other
    path: [file path when file-backed, otherwise source label]
    applies_when: [observable plan-wide condition]
    use_timing: planning|task_execution|review
    required_for: [why executors need this skill context]
evidence_capability:
  result: mapped | no_validation_bearing_obligation
  reason: [non-empty reason]
  invariants: [stable per-invariant capability entries allocated to task IDs]
---

# Implementation Plan: [Plan Goal]

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Introduction

[Short, concrete introduction explaining what this plan implements, which specification it derives from, and the intended outcome.]

## 1. Requirements & Constraints

Use a compact source-spec ID map. Do not paste long specification sections into the plan.

- **SPEC-REQ-001**: `REQ-001` — [one-line execution impact.]
- **SPEC-AC-001**: `AC-001` — [one-line acceptance impact.]
- **SPEC-CON-001**: `CON-001` — [one-line constraint impact.]
- **SPEC-OQ-001**: `OQ-001` — [one-line decision/blocker impact.]
- **PLAN-REQ-001**: [Plan-only execution requirement, if needed.]

## 2. Source Specification & Knowledge

| ID | Type | Path | Required Application |
|---|---|---|---|
| SRC-001 | specification | `.work-bundle/orchestration/spec/active/...` | [How the spec constrains this plan.] |
| CTX-001 | carried-context | `source specification` | [Accepted project knowledge is already carried in the spec; do not require plan executors to read `.work-bundle/knowledge/`.] |

## 2.1 Knowledge Base Update Carry Forward

- **Disposition**: required|not-needed|completed|blocked
- **Closure return**: missing|completed|not-needed|blocked
- **Source**: [Source specification Knowledge Base Update section or review decision.]
- **Review Gate**: [How review should resolve or validate the disposition before archive.]

`Closure return` starts as `missing`. Final review updates it only from validated keep-summarizing return evidence. `archive-plan` aggregates accepted executor-result dispositions whose `related.plan` (or `related_plan`) unambiguously equals the current plan and fails `knowledge-blocked` when an accepted `update`, `supersede`, or `reclassify` requires closure but this return remains `missing` or `blocked`; rejected dispositions, accepted `none`, other-plan handoffs, and task-only handoffs do not trigger promotion.

## 3. Phase Map

| Phase | Name | Path | Status | Depends On | Parallelizable | Completion Gate |
|---|---|---|---|---|---|---|
| phase-001 | [Phase Name] | `.work-bundle/orchestration/plan/active/[plan-id]/phase-001-[slug].md` | Planned | - | true | [Measurable completion gate.] |

## 3.1 Compactness Check

Plans use the minimum orchestration overhead that preserves complete requirement coverage, Truth Basis continuity, independently falsifiable and testable increments, short evidence loops, exact dependencies, disjoint write scopes, validation ownership, bounded failure radius, handoff requirements, and review boundaries. Do not split one mechanical increment when it already satisfies those constraints, and do not split phases or tasks only to mirror template sections, lifecycle labels, file count, or repeated prose.

Every executable task declares the same five-field Truth Basis. When a consequential simplification or compatibility assumption exists, make the earliest ordinary task cheaply falsify it before broad edits. Do not add a risk score, checkpoint phase, or parallel lifecycle.

## 4. Desired Files

| ID | File Type | Path | Purpose | Operation | Related Phase |
|---|---|---|---|---|---|
| FILE-001 | [api|data-model|domain-model|unit-test|page|documentation|other] | `[exact path]` | [Why this file is needed.] | create/update/delete/read | phase-001 |

## 5. Alternatives

- **ALT-001**: [Alternative approach.]
  - **Status**: pending|accepted|rejected
  - **Decision Required Before**: [phase-id/task-id]
  - **Accepted When**: [Deterministic acceptance condition.]
  - **Rejected Because**: [Concrete rejection reason, if rejected.]

## 6. Open Questions

- **OQ-001**: [Question blocking executable implementation.]
  - **Required Decision**: [Specific decision needed.]
  - **Must Be Resolved Before**: [phase-id/task-id]
  - **Fallback If Unresolved**: stop execution|use declared assumption|skip affected task

## 7. Tests

| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |
|---|---|---|---|---|---|---|
| TEST-001 | unit|integration|model-behavior|manual | `[file/module/function/API]` | phase-001 | - | `[command if applicable]` | [Measurable result.] |

Harness-executed integration commands run against the final accepted plan workspace after ordinary task integration and must be Git-observable-state-neutral. Do not declare a plan-level `files.write` envelope.

## 7.1 Contract Groups, Barriers, And Convergence

Use this section when parallel tasks share a stable common contract.

| ID | Common Contract | Establishing Task | Participants | Barrier | Convergence Owner |
|---|---|---|---|---|---|
| CG-001 | `[contract artifact paths]` | task-001 | task-002, task-003 | BAR-001 releases after participants complete or block with handoffs | task-004 |

Required rules:

- Parallel participants depend on the common contract group and accepted prior handoffs, not sibling in-progress implementation.
- The barrier identifies participant tasks, readiness criteria, release condition, and post-barrier validation owner.
- Joint debug, integration tests, cross-branch behavior checks, and stale-peer classification belong to the convergence owner after barrier release.
- Contract groups and barriers must not bypass repository preflight, dependency checks, disjoint write-scope checks, validation, or handoff creation.

## 8. Generated Artifact Verification

Record the verification pass performed after generating the root plan, phases, and tasks.

How to make tasks parallel: create or confirm a stable boundary artifact before branching work, then assign parallel tasks only when dependencies are satisfied and write scopes are disjoint. Use concrete plan evidence such as API contracts, port interfaces, repository contracts, DTO/schema contracts, event schemas, facades, command contracts, pipeline stage contracts, state tables, rule matrices, branch-by-abstraction, or expand-and-contract boundaries. Keep pattern rationale in the planning artifact; generated executor tasks should receive exact objectives, input/output artifacts, allowed and forbidden files, validation, convergence checks, and integration dependencies.

| ID | Check | Scope | Result | Repair |
|---|---|---|---|---|
| VERIFY-001 | source-spec ID coverage maps every implemented requirement, constraint, resolved alternative, and resolved open question to plan/phase/task artifacts. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-002 | Exact artifact paths, source files, target files, dependencies, task ordering, validation commands, and completion criteria are internally consistent. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-003 | Safe parallelization is exposed where dependencies and write scopes allow, and unsafe parallelization is explicitly blocked by dependency or scope evidence. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-004 | Every task, phase, and plan completion path requires `create-handoff` with a compact, sparse YAML `executor-result` handoff whose body stays applicability-based. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-005 | `allocated_rules` and `allocated_skills` cover all material rule/skill conditions from the source specification, affected files, operation type, CodeGraph/Git needs, validation tasks, and any non-WorkBundle rule/skill sources already visible to the agent. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-006 | Compactness, contract group clarity, barrier correctness, co-worker isolation, convergence validation, and contract-only handoff criteria are present where parallel branches share a contract. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |
| VERIFY-007 | Each task carries allocated Truth Basis authority and the earliest ordinary task falsifies consequential assumptions before broad simplification. | plan/phase/task | passed|repaired|blocked | [Same-turn repair or source-spec repair blocker.] |

If any generated artifact drifts from the source specification, omits required spec-ID coverage, contains inconsistent paths or dependencies, lacks validation, lacks allocated rule/skill coverage, or lacks handoff criteria, repair the generated artifacts in the same planning turn and repeat this verification. If the source specification itself has unresolved questions, missing stable IDs, missing evidence, or contradictory instructions, stop for specification repair instead of inventing plan content.

## 9. Completion Criteria

- **DONE-REQ-001**: All requirements are validated or explicitly marked not applicable with reason.
- **DONE-CON-001**: All constraints are validated with concrete evidence.
- **DONE-TEST-001**: Required tests pass or have documented failure reason and remediation task.
- **DONE-ACH-001**: The implementation achieves the stated plan goal.
- **DONE-FILE-001**: Desired files are created, updated, deleted, or confirmed unnecessary.
- **DONE-VERIFY-001**: Generated root plan, phase, and task artifacts were verified against the source specification and repaired for drift, gaps, dependencies, validations, safe parallelization, and handoff requirements before completion.
- **DONE-HANDOFF-001**: Executor invokes `create-handoff` and creates a compact plan-scoped `executor-result` handoff under `.work-bundle/orchestration/handoff/executor/active/` before reporting the root plan as completed or blocked. The handoff carries only applicable continuation and review evidence, including Knowledge Base Update disposition when review must resolve it.

## 10. Related Specifications / Further Reading

- Related specification: `.work-bundle/orchestration/spec/active/...`
- Carried durable-knowledge context, if any: source specification front matter
