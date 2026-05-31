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

`execute-plan` checks sub-agent support before delegation.

- **Sub-agent scheduler**: partition independent tasks with disjoint write scopes into waves; delegate; validate executor handoffs; update task and phase indexes between waves.
- **Single-agent fallback**: execute one executable task per conversation trip when sub-agents are unavailable or unsafe; still require executor-result handoff and status updates.

`execute-plan` does not archive specs, plans, or handoffs. Completion of a phase or plan requires phase- or plan-scoped executor-result handoffs and status updates before `review-plan`.

## Review and Archive

Only `review-plan` may archive completed specification, plan, and handoff artifacts. On failure it creates a repair specification instead of editing source files. On success it archives related active artifacts and refreshes indexes.

## Evaluation Material

Orchestrator eval prompts: `references/evals/orchestration/evals.json`.
