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
    executor/
      active/
      archived/
    orchestration/
      archived/
  docs/
```

Orchestration artifacts live under `.work-bundle/orchestration/` and are not durable knowledge. Do not store specs, plans, or handoffs under `.work-bundle/knowledge/`.

Runtime orchestration rules live under `rules/orchestration/` (Markdown); orch skills cite merged rules from that directory.

## Execution Chain

```text
spec -> plan -> phase -> task -> execute -> handoff
```

- **Specification**: stable requirements, constraints, interfaces, acceptance criteria, alternatives, and open questions. New specifications are shell-first: create the active spec file, preserve the user purpose, and add `Initial User Purpose Evidence` plus a draft requirement breakdown before long evidence gathering.
- **Root plan**: execution strategy, sequencing, phase map, risk handling, validation strategy, and dependency graph.
- **Phase**: a bounded milestone grouping related tasks with only the spec IDs, decisions, files, and tests those tasks need.
- **Task**: one executable unit with exact source files, target files, symbols, steps, validation, completion criteria, and handoff requirements.
- **Execute**: run the selected task, phase, or plan scope; prefer multi-agent subagent scheduler delegation in Codex app contexts when safe, otherwise single-task fallback.
- **Handoff**: record compact executor-result continuation evidence before advancing status.

Downstream executors may read only the related spec, root plan, relevant phase, relevant task, declared prior handoffs, and task-scoped source or test files. They must not read `.work-bundle/knowledge/` directly.

## Skill Authority

Per-role agent instructions live in self-contained orch skills under `skills/orch-*/SKILL.md`:

| Skill | Role |
| --- | --- |
| `orch-create-specification` | Author AI-ready specs under `spec/active/` |
| `orch-create-implementation-plan` | Derive plan, phase, and task files from an active spec |
| `orch-execute-plan` | Run tasks with scheduler or single-agent fallback |
| `orch-create-handoff` | Write compact executor-result handoffs; legacy orchestration handoffs are not active workflow outputs |
| `orch-review-plan` | Verify implementation, repair spec on failure, archive on success |
| `orch-create-document` | Reader-facing docs under `docs/` |
| `orch-doctor` | Read-only develop-rules and orchestrator diagnostics |

Artifact schemas and required sections: `references/assets/orchestration/contract/`.

## Knowledge Gateway

When durable project knowledge is required before specification or planning, use `keep-summarizing` with `ks-what-is-helpful` gateway mode. Do not browse `.work-bundle/knowledge/` directly from orchestration skills.

Typical retrieval policy mapping:

| Skill | Policy |
| --- | --- |
| `orch-create-specification` | `implementation_spec` |
| `orch-create-implementation-plan` | `implementation_plan` |
| `orch-create-document` | `customer_spec` |
| `orch-create-handoff` | executor-result creation is no-retrieval during execution; other use is legacy or explicitly scoped |
| `orch-review-plan` | `implementation_plan` |
| `orch-execute-plan` | `execution` (upstream only; no retrieval during execution) |

These policies are classification and output-grouping hints. They are not stage-gated discovery filters: `orch-create-specification` uses neutral cross-stage discovery through `ks-what-is-helpful`, then the agent classifies candidates against the `implementation_spec` purpose. Query anchors should be polarity-neutral and stage/perspective/status-neutral unless the user purpose explicitly names a stage, status, or perspective as the subject.

Classify retrieved notes as `authority`, `candidate`, `background`, or `blocked`, and surface material supporting, opposing, constraining, unresolved/open-question, obsolete/replaced, and irrelevant-with-reason evidence when applicable. Only `authority` context may shape requirements and executable tasks.

For `orch-create-specification`, create the specification shell first under `spec/active/`, record `Initial User Purpose Evidence`, and add draft requirements derived from the user purpose before extended evidence gathering. Missing supporting authority notes do not automatically block authoring. The agent records neutral anchors, cross-stage retrieval evidence or retrieval gaps, analyzes the user purpose from the prompt and current repository evidence, and uses Design Interrogation only for unresolved intent that evidence cannot answer. Material non-authority evidence stays visible as rationale, traceability, conflict evidence, or open-question input; it must not become requirement text unless resolved by the user or later accepted authority.

Specifications must record source context, the change-driven Extra evidence loop, Open Questions with advised options, Knowledge Base Update disposition, and a body-level `Quality gate: verified|blocked`. A blocked quality gate prevents implementation planning until blocking questions are resolved and the specification is repaired. A verified quality gate is required before `orch-create-implementation-plan` derives root plan, phase, or task artifacts.

After `orch-create-implementation-plan` generates the root plan, phase files, and task files, it runs generated-plan verification against the source specification before completion. The verification checks source-spec ID coverage, exact artifact paths, dependencies, task write scopes, safe parallelization decisions, validation commands, and `create-handoff` requirements. Generated-artifact drift, missing coverage, dependency mistakes, unsafe parallelization, validation gaps, handoff gaps, and internal consistency problems are repaired in the same planning turn and then rechecked. Unresolved source-spec defects still stop planning for specification repair instead of being patched over in generated plan artifacts.

## Execution Modes

Before execution selection, capability checks, delegation, or implementation changes, `orch-execute-plan` resolves every target source repository or local project root separately from the orchestration artifact repository. Each target records `target_kind` and `preflight_kind`:

- `git-backed` targets use `git-clean-worktree` preflight and accepted-baseline handling.
- `local-project` targets use `local-project` preflight evidence that records the absolute root, source, accessibility, and that Git cleanliness is not applicable.

Execution blocks on empty target sets, inaccessible targets, dirty or unresolved Git-backed targets, or unexplained Git-backed changes. It must not reject an explicitly resolved non-Git local project root solely because it is not a Git repository, and it never automatically stashes, commits, resets, restores, cleans, deletes, or otherwise mutates repositories to pass.

After target preflight, CodeGraph is decided per target root. If `.codegraph/` is absent, record no-index fallback and do not initialize CodeGraph. If `.codegraph/` is present and CodeGraph is available, run `codegraph sync <absolute-repository-root>` before graph-derived inspection, delegation instructions, broad browsing, or editing. Same-repository sync operations are serialized. If sync fails, record `sync-failed` and use bounded fallback unless strict graph gating is explicitly required. Git-backed targets rerun clean-worktree preflight after sync; local-project targets rerun local-project preflight evidence. When indexed source changes, run a post-change `codegraph sync <absolute-repository-root>` before final graph impact validation and executor-result handoff.

- **Multi-agent subagent scheduler**: recheck target repositories before each wave; partition independent tasks with disjoint write scopes; delegate only to visible multi-agent subagents; validate compact executor-result handoffs; accept only handoff-proven changes as the next baseline; update active artifacts and indexes between waves.
- **Single-agent fallback**: recheck target repositories immediately before executing one task per conversation trip when multi-agent subagent delegation is unavailable or unsafe; still require a sparse YAML executor-result handoff and status updates.

Scheduler task delegation in this environment must use visible multi-agent subagents. The scheduler verifies the selected delegation surface is user-visible before assigning plan, phase, or task ownership and records the visible subagent reference when the environment provides a name, id, or label. Invisible internal spawn work and cross-conversation delegation must not own delegated implementation work and must not be used as the plan, phase, or task delegation vehicle. `prefer_subagent: true` is permission to prefer safe visible multi-agent subagent delegation only; it cannot bypass delegation safety, preflight, scope, dependency, validation, or handoff gates.

If multi-agent subagent delegation is unavailable, unsafe, or unsupported, execution uses single-agent fallback when that can satisfy the selected target. If fallback cannot satisfy the target, execution stops with a `delegation-visibility` blocker instead of silently delegating to invisible internal spawn work or cross-conversation delegation. Internal helper workers remain allowed for bounded analysis, local summarization, snippet comparison, or other non-delegated support work when task ownership stays in a visible multi-agent subagent or the current single-agent execution path.

Unrelated or unexplained changes block the next wave or task. Execution remains a no-retrieval stage: `orch-execute-plan` does not browse durable knowledge, retrieve knowledge context, or archive specs, plans, or handoffs. Completion of a task, phase, or plan requires an applicability-based compact executor-result handoff and status updates before `orch-review-plan`; continuation state comes from active specifications, plans, phases, tasks, indexes, and executor-result handoffs rather than orchestration handoff artifacts under active continuation.

## Review and Archive

Only `orch-review-plan` may archive completed specification, plan, and handoff artifacts. It assesses validated implementation and review evidence for structural updates before archival. Mixed structural evidence must be delegated to `ks-extract-valuable-points`; design-file-only structural evidence may be delegated to `ks-breakdown-design`. Orchestration may invoke, schedule, or hand off to the approved `ks-*` owner and consume its result, but it must never directly create, edit, promote, delete, or index durable knowledge.

Review provides the target project, reviewed specification and plan, relevant executor-result handoffs, validation evidence, changed files or symbols, structural-update summary, and Knowledge Base Update disposition carried from the source specification or root plan. The delegated `ks-*` owner returns its structural-value result, written or updated durable paths or an evidence-backed no-write rationale, index rebuild status, blockers, and completion state. Review validates that return, resumes disposition evaluation, and keeps archive blocked if delegation is unavailable or evidence is incomplete. On failure it creates a repair specification instead of editing source files. On success, and only when Knowledge Base Update disposition is `completed` or `not-needed`, it archives related active artifacts and refreshes orchestration indexes.

## Evaluation Material

Orchestrator eval prompts: `references/evals/orchestration/evals.json`.
