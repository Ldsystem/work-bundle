# Orchestration Workflow

## Project Orchestration Layout

```text
.work-bundle/orchestration/
  spec/
    active/
    archived/
  plan/
    active/
    archived/
  handoff/
    orchestration/
      active/
      archived/
    executor/
      active/
      archived/
  docs/
```

Orchestration artifacts live under `.work-bundle/orchestration/` and are not durable knowledge. Do not store specs, plans, or handoffs under `.work-bundle/knowledge/`.

## Execution Chain

```text
spec -> plan -> phase -> task -> execute -> handoff
```

- **Specification**: stable requirements, constraints, interfaces, acceptance criteria, alternatives, and open questions.
- **Root plan**: execution strategy, sequencing, phase map, risk handling, validation strategy, and dependency graph.
- **Phase**: a bounded milestone grouping related tasks with only the spec IDs, decisions, files, and tests those tasks need.
- **Task**: one executable unit with exact source files, target files, symbols, steps, validation, completion criteria, and handoff requirements.
- **Execute**: run the selected task, phase, or plan scope; prefer sub-agent scheduling when safe, otherwise single-task fallback.
- **Handoff**: record executor or orchestration continuation evidence before advancing status.

Downstream executors may read only the related spec, root plan, relevant phase, relevant task, declared prior handoffs, and task-scoped source or test files. They must not read `.work-bundle/knowledge/` directly.

## Directive Authority

Per-role agent instructions live under `references/directives/orchestration/`:

| Directive | Role |
| --- | --- |
| `create-specification` | Author AI-ready specs under `spec/active/` |
| `create-implementation-plan` | Derive plan, phase, and task files from an active spec |
| `execute-plan` | Run tasks with scheduler or single-agent fallback |
| `create-handoff` | Write orchestration or executor-result handoffs |
| `review-plan` | Verify implementation, repair spec on failure, archive on success |
| `create-document` | Reader-facing docs under `docs/` |
| `doctor` | Read-only develop-rules and orchestrator diagnostics |

Artifact schemas and required sections: `references/assets/orchestration/contract/`.

## Knowledge Gateway

When durable project knowledge is required before specification or planning, use `keep-summarizing` with `what-is-helpful` gateway mode. Do not browse `.work-bundle/knowledge/` directly from orchestration directives.

Typical retrieval policy mapping:

| Directive | Policy |
| --- | --- |
| `create-specification` | `implementation_spec` |
| `create-implementation-plan` | `implementation_plan` |
| `create-document` | `customer_spec` |
| `create-handoff` | `implementation_plan` |
| `review-plan` | `implementation_plan` |
| `execute-plan` | `execution` (upstream only; no retrieval during execution) |

Classify retrieved notes as `authority`, `candidate`, `background`, or `blocked`. Only `authority` context may shape requirements and executable tasks.

## Execution Modes

Before execution selection, capability checks, delegation, or implementation changes, `execute-plan` resolves every target source repository separately from the orchestration artifact repository and runs read-only clean-worktree preflight. It blocks on dirty, unresolved, inaccessible, non-Git, or empty target sets and never automatically stashes, commits, resets, restores, cleans, deletes, or otherwise mutates repositories to pass.

- **Sub-agent scheduler**: recheck target repositories before each wave; partition independent tasks with disjoint write scopes; delegate; validate executor handoffs; accept only handoff-proven changes as the next baseline; update task and phase indexes between waves.
- **Single-agent fallback**: recheck target repositories immediately before executing one task per conversation trip when sub-agents are unavailable or unsafe; still require executor-result handoff and status updates.

Unrelated or unexplained changes block the next wave or task. Execution remains a no-retrieval stage: `execute-plan` does not browse durable knowledge, retrieve knowledge context, or archive specs, plans, or handoffs. Completion of a phase or plan requires phase- or plan-scoped executor-result handoffs and status updates before `review-plan`.

## Review and Archive

Only `review-plan` may archive completed specification, plan, and handoff artifacts. It assesses validated implementation and review evidence for structural updates before archival. Mixed structural evidence must be delegated to `ks-extract-valuable-points`; design-file-only structural evidence may be delegated to `ks-breakdown-design`. Orchestration may invoke, schedule, or hand off to the approved `ks-*` owner and consume its result, but it must never directly create, edit, promote, delete, or index durable knowledge.

Review provides the target project, reviewed specification and plan, relevant handoffs, validation evidence, changed files or symbols, expected durable conclusions, structural-update summary, and current disposition. The delegated `ks-*` owner returns its structural-value result, written or updated durable paths or an evidence-backed no-write rationale, index rebuild status, blockers, and completion state. Review validates that return, resumes disposition evaluation, and keeps archive blocked if delegation is unavailable or evidence is incomplete. On failure it creates a repair specification instead of editing source files. On success, and only when knowledge-update disposition is `completed` or `not-needed`, it archives related active artifacts and refreshes orchestration indexes.

## Evaluation Material

Orchestrator eval prompts: `references/evals/orchestration/evals.json`.
