---
name: orch-execute-plan
description: 'Execute implementation plans through scheduler delegation or single-agent fallback.'
---

# orch-execute-plan

## Scope

Execute implementation plans through multi-agent subagent scheduler delegation in Codex app contexts or single-agent fallback.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

Prefer the smallest requested target: task, then phase, then plan. If given a task, execute that task only. If given a phase or plan and multi-agent subagent delegation is supported, the main agent acts as scheduler and advances through executable tasks until the selected target is complete or blocked. If multi-agent subagent delegation is unavailable, forbidden, or unsafe, use the single-agent fallback and execute one task only, or report a `delegation-visibility` blocker when fallback cannot satisfy the requested scope.

## Context Boundary

Allowed:

- referenced specs under `.work-bundle/orchestration/spec/`;
- active plans, phases, and tasks under `.work-bundle/orchestration/plan/`;
- explicitly referenced executor handoffs under `.work-bundle/orchestration/handoff/executor/`;
- source and test files directly required by executable tasks.

Forbidden:

- `.work-bundle/knowledge/`;
- raw chat logs;
- unrelated specs, plans, tasks, handoffs, or docs;
- broad repository exploration;
- architecture, API, data model, dependency, or durable-knowledge decisions not declared by the task.

Execution must use context already carried by the specification, plan, phase, task, and declared handoffs. Although `execute-plan` maps to the `execution` retrieval policy for upstream artifact preparation, execution itself must not run v3 retrieval queries, invoke `what-is-helpful`, or promote candidate/background notes while executing.

## Execution Constraints (skill-owned)

The scheduler-owned and executor-owned sections below are the skill-owned execution constraints. They preserve clean-worktree preflight, target repository resolution, CodeGraph fallback, visible multi-agent subagent delegation, single-agent fallback, and executor-result handoff requirements.

## Scheduler-Owned Constraints

The scheduler owns target selection, dependency scheduling, delegation safety, visible subagent evidence, and aggregation. It does not implement task-scoped source changes.

### Selection and Scheduling

- Resolve effective `prefer_subagent` as project metadata first, then global bootstrap, then `false`: `.work-bundle/project.yaml` -> `prefer_subagent`, `$work_bundle_config_root/bootstrap.yaml` -> `prefer_subagent`, fallback `false`.
- Treat `prefer_subagent: true` only as permission to prefer the multi-agent subagent scheduler when all existing safety checks pass.
- Treat `prefer_subagent: false` as a preference for single-agent fallback unless the user explicitly requests safe scheduler delegation for the current target.
- Resolve target in order: task ID/path -> execute that task only; phase ID/path -> select all executable tasks in that phase, respecting dependencies; plan ID/path -> select executable phases and tasks in dependency order; no executable task -> report blocker and stop.
- An executable task has status `Planned` or `In progress`, satisfied dependencies, resolved required decisions, available source files, and no missing required handoff.
- Before capability checks, delegation, or fallback execution, read allocated rules and skills from the selected task, parent phase, and root plan. Build a compact executor context listing relevant `allocated_rules` and `allocated_skills`, their source, file path when file-backed, load/use timing, enforcement, and required-for reasons. Do not assume allocated skills come only from `$work_bundle_root/skills` or allocated rules come only from WorkBundle rule indexes; allocations may also come from `AGENTS.md`, WorkBundle project/global/toolkit scopes, builtin rules, `.agents/skills`, `.codex/skills`, plugin skills, or other agent-visible rule/skill instructions.
- Block or repair the artifact before execution when a selected task lacks allocated rule/skill context for material source-code, script, rule, skill, workflow, contract, Git, CodeGraph, metadata preflight, or validation work.
- If effective `prefer_subagent` is `true`, multi-agent subagent delegation is supported, and the selected target has one or more safe executable tasks, use the sub-agent scheduler path.
- If effective `prefer_subagent` is `false`, multi-agent subagent delegation is unavailable, disabled by the user, blocked by the environment, or unsafe because scopes overlap or the next step depends on a single result, use the single-agent fallback.
- If multi-agent subagent delegation is unavailable or unsafe and single-agent fallback cannot satisfy the selected target, stop with a `delegation-visibility` blocker. Do not silently delegate to invisible internal spawn work or cross-conversation delegation.
- Do not fail only because multi-agent subagent delegation support is missing when single-agent fallback is valid. Record fallback reason in the result and handoff.
- Never allow `prefer_subagent` to bypass visible delegation safety, repository preflight, accepted-baseline checks, disjoint write scopes, dependency checks, handoff requirements, or the single-agent fallback.
- Invisible internal spawn workers and cross-conversation delegation must not own delegated plan, phase, or task implementation work. Internal workers may be used only for bounded helper analysis, local summarization, snippet comparison, or other support work that does not own delegated execution and does not replace multi-agent subagent task delegation.
- Detect contract groups and barriers declared by the root plan, parent phase, selected task, accepted executor-result handoffs, or the shared workflow contract before scheduling a parallel wave.
- For contract-decoupled waves, treat the common contract group and accepted prior handoffs as the validation baseline. Do not treat sibling in-progress implementation files, sibling unaccepted handoffs, or pre-barrier cross-branch checks as dependencies.
- Do not classify sibling in-progress branch output as stale, missing, contradictory, or required unless an accepted handoff dependency or a post-barrier convergence task explicitly declares that relationship.
- Schedule convergence, joint-debug, integration validation, or cross-branch tests only after every participant in the matching barrier has completed or blocked with an executor-result handoff.

### Delegation and Aggregation

- Build the current execution queue from tasks whose dependencies are satisfied.
- Partition the queue into waves of independent tasks with disjoint write scopes.
- Keep contract-decoupled barrier participants in the same safe wave when their write scopes are disjoint and their only shared dependency is the established common contract group.
- Recheck every target repository for the wave against the initial or accepted-handoff baseline; block the entire wave on any unexplained change.
- Delegate each task in the wave to a separate visible multi-agent subagent when scopes allow parallel execution. Before assignment, verify that the delegation surface is user-visible; if not, use single-agent fallback or stop with a `delegation-visibility` blocker.
- Record the visible delegation reference for each task when the environment provides a subagent id, visible label, or other user-visible reference. Record `internal_spawn_used_for_task_delegation: false`.
- Give every visible delegated worker the assigned task path, relevant spec, plan, and phase paths; allowed source and target files/modules; exact validation required by the task; and the instruction to avoid invisible internal spawn work or cross-conversation delegation.
- For contract-decoupled tasks, give every visible delegated worker the common contract group id, exact common contract artifact paths, accepted prior handoff ids or paths, forbidden peer validation scope, barrier id, convergence owner, and the instruction to validate only against the common contract, accepted prior handoffs, task-local files, and declared validation commands.
- Give every visible delegated worker the allocated rules and skills from the task, parent phase, and root plan, including each allocation's source and file path when file-backed, with explicit instruction to load, use, acknowledge, or condition-evaluate them before implementation and to record unavailable or inapplicable allocation in its handoff.
- Require each visible delegated worker to record `task_fit_check`, `internal_spawn_used_for_task_delegation: false`, its visible reference when available, and a sparse YAML `executor-result` handoff before exit.
- Wait for all visible delegated workers in the active wave to finish.
- Validate each executor handoff against the task, parent phase, root plan, and source specification.
- Accept only compact executor-result handoffs whose fields satisfy applicability rules: assigned task, result summary, changed files or inspected artifacts, validation evidence, unresolved blockers when present, `task_fit_check`, repository/preflight or accepted-baseline evidence when relevant, compact CodeGraph evidence when source-code work was in scope, and `delegation_evidence` when ownership was delegated or fallback proof is required.
- For contract-decoupled task handoffs, also require `contract_decoupling` evidence with `common_contracts_checked`, `peer_implementation_validation_used: false`, validation scope limited to common contracts, accepted prior handoffs, and task-local files, plus barrier participation readiness when the task is a barrier participant.
- Reject or mark unresolved any pre-barrier handoff that validates against sibling in-progress source files, sibling unaccepted handoffs, or cross-branch behavior before the declared barrier release.
- Mark barrier participants ready only after their executor-result handoffs are valid. Release the barrier for convergence work only when all participants have valid completed or blocked handoffs.
- If a handoff is valid and completion criteria are satisfied, mark the task `Completed`; if partial or blocked, mark `On Hold` or keep `In progress` with the blocker.
- Refresh task status in the parent phase file and root plan task/phase indexes.
- Build the next accepted-handoff baseline only from validated handoff evidence, then continue with the next executable wave until the selected task, phase, or plan is complete or blocked.

### Completion Coordination

- After valid task handoffs show all tasks in a phase are complete, validate phase completion criteria, update phase status to `Completed`, update the phase status in the root plan file, and invoke `create-handoff` for a phase-scoped `executor-result` handoff.
- After all phases in a plan are complete, validate plan completion criteria, update plan status to `Completed`, and invoke `create-handoff` for a plan-scoped `executor-result` handoff.
- Keep phase and plan handoffs compact and applicability-based: completed tasks or phases, changed or inspected artifacts, validation evidence, unresolved blockers when present, repository/CodeGraph/delegation evidence when relevant, and task-fit or phase-fit or plan-fit evidence sufficient for continuation or review.
- Preserve barrier state in phase and plan handoffs when applicable: common contract group, participant handoff ids, barrier readiness, convergence owner, and whether convergence checks remain pending.
- Do not archive specs, plans, phases, tasks, or handoffs during execution. Archival belongs only to `review-plan`.

## Status

Use:

```text
Planned | In progress | Completed | Deprecated | On Hold
```

Do not mark a task, phase, or plan completed unless criteria are satisfied or incomplete validation is explicitly documented with a remediation path.

## Executor-Owned Constraints

The executor owns task-scoped execution and must not expand into scheduler work.

## Repository Preflight

- Use only carried spec, plan, phase, task, and declared handoff context.
- Do not load `.work-bundle/knowledge/`, run v3 retrieval, or invoke `what-is-helpful`.
- Follow the selected task exactly and modify only task-scoped files unless the task explicitly expands scope.
- Before execution selection, capability checks, delegation, or implementation-file modification, resolve every target source repository or local project root separately from the orchestration artifact repository.
- Prefer project metadata source repositories from `$project_root/.work-bundle/project.yaml` before falling back to task scopes or explicit references, while preserving exact task-scoped target resolution.
- For Git-backed metadata targets, compare actual branch and HEAD commit against metadata `working_branch` and `last_commit_id` before accepting clean-worktree status. Block on `branch-mismatch`, `stale-baseline`, missing required metadata, or registry/project contradiction unless a validated accepted-handoff baseline explains the state.
- Record metadata baseline evidence for every target repository: repository id when available, expected and actual branch, expected and actual commit, branch status, commit or baseline status, and CodeGraph support/no-index state.
- Record `target_kind=git-backed` for Git repositories and `target_kind=local-project` for explicitly resolved non-Git local roots. Record the matching `preflight_kind`, such as `git-clean-worktree` or `local-project`.
- Run repository preflight before implementation or file modification. Require every Git-backed target repository to report `clean` from `git status --porcelain=v1 --untracked-files=all`; block on dirty, unresolved, inaccessible, or missing-file cases.
- Block when no target repository resolves or any Git-backed target reports `dirty`, unresolved, inaccessible, missing, or unexplained changes.
- Do not reject an explicitly resolved non-Git local project root solely as `not-git`; record local-project evidence when Git clean-worktree checks do not apply.
- Do not fabricate Git cleanliness evidence for local-project targets. Record the absolute root, source, accessibility, and that Git clean-worktree preflight is not applicable.
- Never alter pre-existing changes to pass preflight. If a required file is missing, unresolved, or inaccessible, stop and report the blocker.
- After accepting validated executor-result handoffs, build accepted-baseline JSON only from proven prior outputs and block on any unrelated or unexplained current entry.
- Accepted baselines explain only expected worktree changes. They do not override branch mismatch, inaccessible repositories, missing required metadata, or CodeGraph policy violations.
- For contract-decoupled parallel work, accepted baselines may include the common contract task handoff and prior validated participant handoffs only. They must not include sibling in-progress work, unaccepted sibling handoffs, raw agent claims, or files outside the assigned validation scope.

### Allocated Rule and Skill Context

- Load, use, acknowledge, or condition-evaluate task-level `allocated_rules` before implementation according to each entry's source, `load_timing`, and `enforcement`.
- Use or acknowledge task-level `allocated_skills` according to each entry's source, `use_timing`, and `required_for` reason.
- When phase-level or root-plan allocation applies to the selected task, carry it into worker instructions or single-agent fallback notes.
- Do not rely on workers to rediscover allocation from global rule indexes when the generated task already declares allocation.
- Record allocation handling in task-fit or validation evidence when a rule or skill is unavailable, stale, inapplicable, or materially affects execution.

### Accepted Baseline

Accepted Baseline evidence must come only from validated executor-result handoffs. Do not treat unverified worktree changes, raw agent claims, raw chat logs, or unrelated dirty files as accepted baseline input.

### CodeGraph and Fallback

- After repository preflight passes, decide CodeGraph applicability per target root.
- If the target root has no `.codegraph/`, record CodeGraph as skipped with reason `no-index` and use bounded fallback through direct file reads or text search. Do not initialize CodeGraph and do not run `codegraph sync` for no-index roots.
- If `.codegraph/` exists and CodeGraph is available, run `codegraph sync <absolute-repository-root>` after the applicable target preflight and before graph-derived source inspection or implementation. Then query CodeGraph for the task-relevant symbol, file, or call-path evidence before broad text search.
- If `codegraph sync <absolute-repository-root>` fails, record `sync-failed`, use bounded fallback for that repository, and block only when the task or user explicitly requires strict graph gating.
- For Git-backed targets, rerun repository preflight after a successful pre-inspection sync and before implementation begins.
- When a task changes indexed source in a CodeGraph-enabled target, run a post-change `codegraph sync <absolute-repository-root>` before final graph impact validation and before the executor-result handoff.
- Executor-result handoffs must record compact CodeGraph evidence by applicability, including repository root, applicability, `up_to_date`, and required fallback or blocker facts such as `no-index`, `sync-failed`, `stale`, or `blocked`.

### Implementation, Validation, and Handoff

- Verify the implementation against the related specification, root plan, parent phase, and assigned task before handoff.
- Repair every task-scoped drift or gap and recheck until clean.
- Record explicit drift/gap verification evidence in `task_fit_check`, including the artifacts checked and final recheck result.
- Treat newly discovered upstream/downstream conflicts, validation failures, failed validation commands, missing validation/test artifacts, and user corrections as task-fit drift/gap evidence.
- Trigger `wb-violation-evaluation` when execution-time conflicts, violations, errors, failed validations, contradictory workflow behavior, user interruptions, or user corrections make WorkBundle process responsibility plausible.
- `wb-violation-evaluation` is a bounded relatedness check: stop once visible evidence shows WorkBundle skill, rule, script, specification, plan, handoff, or workflow-contract relevance; do not require chain-of-thought output, exhaustive root-cause tracing, or treating example workflow chains as mandatory fix patterns.
- Executor-result handoffs for source-code or toolkit-contract work must state whether new upstream/downstream impact evidence or validation/test evidence was found during execution and whether it was repaired, blocked, or out of scope.
- Contract-decoupled executor-result handoffs must state whether validation used peer implementation output. The required passing value before convergence is `peer_implementation_validation_used: false`.
- Barrier participant executor-result handoffs must record barrier readiness as `reached` or `blocked`; convergence owners must record that all participant handoffs were completed or blocked before joint validation started.
- Run declared validation when possible and record skip reasons when not.
- Validation failures, unresolved blockers, unavailable required capabilities, or missing files block completion until repaired or explicitly documented.
- Create a sparse YAML executor-result handoff before exit with applicable changed files, validation, task-fit, repository/preflight or accepted-baseline evidence, compact CodeGraph evidence, and `delegation_evidence` when delegation occurred.
- Include compact metadata baseline evidence and allocated rule/skill handling in the executor-result handoff when execution used project metadata or allocated context.
- Update the assigned task status and parent phase task map when criteria are met or a blocker is known.
- Do not create orchestration handoffs or archive during execution.

### Execution Output

```text
Execution blocked.
Target: <plan|phase|task id/path>
Execution path: sub-agent-scheduler|single-agent-fallback
Blocker: <specific blocker>
Questions asked: <0|1|2>
Required action: <specific action>
Repository preflight:
- <absolute target repository> | source=<resolution source> | baseline=initial|accepted-handoff | status=dirty|unresolved|inaccessible|not-git | changes=<changed/staged/deleted/untracked or unexplained paths>
Delegation:
- delegated=<true|false> | surface=<multi-agent-subagent|single-agent-fallback|internal-helper-worker|none> | visible_reference=<subagent id, visible label, or not-provided> | internal_spawn_used_for_task_delegation=false | fallback_reason=<reason or null>
Files changed:
- <path or none>
Handoff: <path or required create-handoff action>
```

```text
Execution result: completed|partially-completed|failed
Target: <plan|phase|task id/path>
Execution path: sub-agent-scheduler|single-agent-fallback
Repository preflight:
- <absolute target repository> | source=<resolution source> | baseline=initial|accepted-handoff | status=clean|blocked
Delegation:
- delegated=<true|false> | surface=<multi-agent-subagent|single-agent-fallback|internal-helper-worker> | visible_reference=<subagent id, visible label, or not-provided> | internal_spawn_used_for_task_delegation=false | internal_workers_used_for_support=<true|false> | fallback_reason=<reason or null>
Executed:
- <task id/path>
Files changed:
- <path>
Validation:
- <test/command>: passed|failed|skipped
Handoffs:
- <path>
Status updates:
- <task|phase|plan id>: <status>
Continuation state: <completed target or next executable target when still in execution scope>
```

## Validation

Confirm repository preflight ran before selection/capability checks/delegation/modification, every target source repository was resolved and recorded separately from the orchestration artifact repository, project metadata `working_branch` and `last_commit_id` were checked when available, metadata baseline blockers were honored, allocated_rules and allocated_skills were loaded or condition-evaluated before implementation, every target passed initial preflight, rechecks ran before each wave or fallback task, accepted baselines came only from validated executor-result handoffs, unexplained changes blocked execution, no repository cleanup or mutation was attempted, no `.work-bundle/knowledge/` files were loaded or modified, only relevant execution artifacts were loaded, only task-scoped files changed, multi-agent subagent delegation support was checked, `prefer_subagent` remained permission-only and did not bypass delegation safety, scheduler mode used multiple visible delegated workers when safe parallel work existed, invisible internal spawn work and cross-conversation delegation did not own delegated plan/phase/task execution, fallback mode executed only one task or a `delegation-visibility` blocker was reported, internal helper workers were used only for bounded non-delegated support when present, every delegated or fallback executor verified its implementation against the related specification, root plan, parent phase, and assigned task before handoff, every task-scoped drift or gap was repaired and rechecked, unresolved out-of-scope findings blocked completion, every executor handoff includes compact `task_fit_check` drift/gap verification evidence, every delegated executor created a sparse YAML executor handoff with `delegation_evidence` and updated task status before exit, accepted handoffs were validated against task/phase/plan/spec, phase and plan sparse executor-result handoffs were created when those targets completed, validation status is recorded, changed files or inspected artifacts are recorded, no forbidden executor advice fields are present, no more than 2 blocking questions were asked, and no archive operation occurred during execution.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`

## Rule Loading (mandatory)

Before substantive execution work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive orchestration work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or directive summaries as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress orchestration task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Boundary

Platform write boundary and durable-knowledge prohibition: follow `orch-orchestration-boundary` (`rules/orchestration/orch-orchestration-boundary.md`).

> **Deprecation:** The role-context subsystem is deprecated; see spec §0.9 in `spec-process-orch-skill-rule-boundary-optimization-20260611`. Do not invoke it from orch skills.
