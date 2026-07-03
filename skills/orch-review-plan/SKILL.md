---
name: orch-review-plan
description: 'Review completed implementation and archive or create repair specifications.'
---

# orch-review-plan

## Scope

Review completed implementation and archive or create repair specifications.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

For v3 knowledge, validation-backed promotion requires front matter evidence in durable notes when a note is promoted to `implemented` or when `current` is promoted from `implemented`. When review needs durable knowledge, use the `implementation_plan` retrieval policy through `keep-summarizing` gateway mode. Review may recommend durable knowledge extraction through `keep-summarizing`, but it must not silently write durable knowledge or treat candidate/background retrieval as implemented authority.

Review output must include a final line in this exact form: `Knowledge update disposition: completed|not-needed|blocked|required`.

## Context Boundary

Allowed:

- related active specification under `.work-bundle/orchestration/spec/active/`;
- related active plan, phase, and task files under `.work-bundle/orchestration/plan/active/`;
- related executor-result handoffs under `.work-bundle/orchestration/handoff/`;
- legacy orchestration handoffs only when already linked by an active artifact, index row, or repair/review history;
- project files explicitly referenced by the specification, plan, task files, or handoffs;
- durable project knowledge only if retrieved through `keep-summarizing` `what-is-helpful` gateway mode.

Forbidden:

- direct browsing of `.work-bundle/knowledge/`;
- raw chat logs;
- unrelated specs, plans, tasks, handoffs, docs, or project files;
- source edits, migrations, implementation fixes, or task execution.

## Inputs

Resolve:

- target plan ID/path;
- source specification ID/path;
- all active phase and task files for the plan;
- task-scoped and phase/plan-scoped executor handoffs;
- relevant project files referenced by the resolved artifacts.

Stop if the plan or source specification cannot be resolved.

## Review Procedure

Validate:

1. specification requirements, constraints, interfaces, and acceptance criteria are represented in the plan;
2. plan phases and tasks cover the specification without unsupported scope expansion;
3. executor-result handoffs exist for completed or partial task, phase, and plan scopes and include compact fields by applicability: changed files or inspected artifacts, validation commands/results, unresolved blockers, task-fit check, repository/preflight evidence, CodeGraph evidence, and delegation evidence;
4. phase and plan handoffs exist when those scopes are marked `Completed`;
5. project files reflect the implementation claimed by the handoffs;
6. validation evidence satisfies the task, phase, plan, and specification criteria;
7. statuses are coherent across task files, phase task indexes, root plan phase indexes, handoff statuses, and indexes;
8. no required artifact is missing, stale, contradictory, or under `.work-bundle/knowledge/`;
9. the source specification `Knowledge Base Update` section is reflected in the final review state, including expected durable conclusions, evidence, and follow-up path;
10. validated implementation and review evidence is assessed for structural updates;
11. the final knowledge-update disposition is one of `completed`, `not-needed`, `blocked`, or `required`, with evidence for that outcome.
12. reviewed source repository state is ready for archive: required commit, applicable CodeGraph sync, and project metadata update gates have completed or are explicitly not applicable with reason.
13. specification-included violation evidence is evaluated against the reviewed implementation, validation, and handoffs before archive.
14. specification-carried unsettled notes, opposite evidence, candidate/background evidence, and other material non-authority inputs are settled before archive when they affect requirements, workflow, policy, validation, execution behavior, or durable knowledge disposition.

Reject review when a compact executor-result handoff omits applicable safety evidence or marks it inapplicable without a concrete reason. Required-by-applicability checks include:

- `changes.files` when files, symbols, artifacts, schemas, commands, or docs changed or were inspected;
- `validation.commands` when any command, test, lint, inspection, or intentional skip occurred;
- `unresolved` when blockers or unresolved issues remain;
- `task_fit_check` for completed or partial task results, with the assigned task, result, checked specification/root-plan/phase/task artifacts, and meaningful findings;
- `repository` when preflight, accepted-baseline, changed-path, or blocker state matters for continuation.

For completed source-code tasks, reject review when applicable CodeGraph evidence is missing, stale, contradictory, or marked inapplicable without a reason. Required compact evidence includes a `codegraph:` block per source-code target repository with `root`, `applicable`, `up_to_date`, and the needed fallback or blocker fact. Indexed source-code work must still prove index presence, sync/query or explored-symbol evidence, post-change sync when indexed source changed, and final graph impact/up-to-date result, but review must not require fixed Markdown section headings or verbose field names when the compact evidence is semantically complete. Accepted fallback reasons include `no-index`, `sync-failed`, `not-source-code`, or `blocked`.

For delegated task, phase, or plan work, reject review when visible-delegation evidence is missing, contradictory, or marked inapplicable without a reason. Required evidence is compact `delegation_evidence`, not orchestration advice: delegated flag, delegation surface, `visible_reference` when the environment provides one, `internal_spawn_used_for_task_delegation: false`, internal helper-worker usage if any, and a fallback or blocker reason when visible threads/worktrees were unavailable or unsafe. Internal helper-worker use is acceptable only when the handoff shows it did not own delegated task execution.

For specification-included violation evidence, reject review or keep archive blocked when an included blocking violation remains unresolved, cannot be closed, contradicts the reviewed implementation, or lacks lifecycle evidence for the closure decision. Close included violations only during passing, unblocked review when the reviewed implementation resolves the behavior and archive is otherwise allowed. Use the approved violation lifecycle helper or equivalent bounded operation; do not delete evidence files or close unrelated violation records.

For specification-carried unsettled material, record a settlement result before archive for each material item: resolved by implementation, no longer applicable, promoted or delegated through approved `ks-*` follow-up, still blocked, or explicitly non-blocking with rationale. Keep archive blocked when unsettled material remains unresolved and affects requirements, workflow, policy, validation, execution behavior, or durable knowledge disposition.

## Delegate-Return-Resume Protocol

When review identifies a structural update:

1. set or retain `Knowledge update disposition: required`;
2. delegate mixed implementation, validation, handoff, and review evidence to `ks-extract-valuable-points`; use `ks-breakdown-design` only when the structural evidence is design-file-only;
3. provide the target project identity, reviewed specification, plan, relevant handoffs, validation evidence, changed project files or symbols, expected durable conclusions, structural-update summary, and current disposition;
4. leave structural-value assessment, persistence routing, `ks-write-knowledge` follow-up, and index rebuilds exclusively to the delegated `ks-*` workflow;
5. require the delegated workflow to return its structural-value result, written or updated durable knowledge paths, evidence-backed no-write rationale when applicable, index rebuild status, blockers, and completion state;
6. validate the returned evidence and then resume knowledge-update disposition evaluation.

After review resumes:

- set disposition to `completed` only when the delegated return identifies written or updated durable paths and reports successful index rebuild status;
- set disposition to `not-needed` only when the delegated structural-value assessment safely concludes that no durable write is warranted, includes an evidence-backed no-write rationale, and reports index status;
- keep disposition `required` or `blocked` when delegation is unavailable, incomplete, contradictory, blocked, or lacks required return evidence;
- do not archive until all other review checks pass and disposition is `completed` or `not-needed`.
- settle specification-carried unsettled material with validated implementation, validation, and delegated return evidence before archive.

Review may invoke, schedule, or hand off to the approved `ks-*` owner and consume its result. Review must not directly create, edit, promote, delete, or index `.work-bundle/knowledge/**`.

## Failure Path

If any review check fails:

- do not archive artifacts;
- create a new active repair specification under `.work-bundle/orchestration/spec/active/`;
- include discrepancies, evidence, affected spec/plan/handoff/project files, severity, required fixes, and acceptance criteria;
- link the repair specification to the reviewed plan and related handoffs;
- report the repair specification path and the next `create-implementation-plan` or `execute-plan` action.
- if the knowledge update disposition remains `required`, report that archival is blocked and provide an actionable `ks-extract-valuable-points` delegation input for mixed implementation/review evidence or `ks-breakdown-design` input when the evidence source is design-file-only;
- if delegation cannot run in the active environment or returned evidence is incomplete, keep review blocked, report the missing delegation action or evidence, and do not archive;
- if the knowledge update disposition is `blocked` without an actionable blocker path, treat the review as failed and require repair rather than archive.
- if specification-included violation closure cannot be completed or an included blocking violation remains unresolved, keep review blocked or failed and do not archive.
- if specification-carried unsettled material remains material and unsettled, keep review blocked or failed and do not archive.

The repair specification must be actionable without raw chat history.

## Success Path

If all review checks pass and the knowledge update disposition is `completed` or `not-needed`:

- close resolved specification-included violation evidence as `completed` before archive, using approved lifecycle operations and recording the closure evidence in review output;
- record settlement of specification-carried unsettled material before archive, including any delegated `ks-*` return evidence or explicit non-blocking rationale;
- inspect `.work-bundle/project.yaml` `operation_policy.git` before any Git stage or commit action;
- create an allowed Git commit for reviewed source changes when commit is permitted and there are staged or stageable reviewed changes; do not commit unrelated or unexplained changes;
- run or require post-review CodeGraph sync only for changed source repositories whose project metadata has `codegraph.supported: true`, `codegraph.index_present: true`, and an actual `.codegraph/` marker; do not run `codegraph sync` for no-index repositories;
- update `.work-bundle/project.yaml` source repository state after successful review commit and applicable CodeGraph sync, including `working_branch`, `last_commit_id`, `baseline_status`, and CodeGraph `status`/`synced_commit_id` when applicable;
- block archive when a required commit, applicable CodeGraph sync, or project metadata update fails, unless the operation is not allowed or not applicable and the review output records the concrete reason;
- mark related executor-result handoffs `reviewed`, then archive them;
- archive linked legacy orchestration handoffs only when they are part of the reviewed artifact set;
- archive the related source specification;
- archive the related root plan file, phase files, and task files;
- refresh spec, plan, and handoff indexes;
- report archived paths and state that the plan is review-complete.

Archival means moving files from `active/` to the corresponding `archived/` directory. Do not delete files.

Do not archive when the knowledge update disposition is `required`, when it is `blocked` without an actionable blocker path, when specification-included violation closure is incomplete, when material specification-carried evidence remains unsettled, or when required commit, CodeGraph sync, or project metadata update gates are incomplete. Those outcomes are blocked or failed review states, not success states.

## Helper Commands

Use deterministic helpers when available:

```text
scripts/orch.py set-spec-status --id <spec-id> --status archived
scripts/orch.py archive-plan --id <plan-id>
scripts/orch.py set-handoff-status --id <handoff-id> --status archived
scripts/orch.py index-specs
scripts/orch.py index-plans
scripts/orch.py index-handoffs
```

If helpers are unavailable, perform equivalent moves only under `.work-bundle/orchestration/` and refresh indexes.

## Blocked Output

```text
Review blocked.
Target: <plan id/path>
Blocker: <specific blocker>
Required action: <specific action>
Knowledge update disposition: blocked|required
No files archived.
```

## Failure Output

```text
Review result: failed
Target: <plan id/path>
Repair specification: <path>
Findings:
- <finding with evidence>
Next action: <create-implementation-plan|execute-plan target>
Knowledge update disposition: blocked|required
No files archived.
```

## Success Output

```text
Review result: passed
Target: <plan id/path>
Archived:
- <spec path>
- <plan/phase/task paths>
- <handoff paths>
Indexes refreshed:
- .work-bundle/orchestration/spec/index.jsonl
- .work-bundle/orchestration/plan/index.jsonl
- .work-bundle/orchestration/handoff/index.jsonl
Next action: none
Knowledge update disposition: completed|not-needed
```

## Validation

Confirm reviewed artifacts match the requested plan, durable knowledge was accessed only through `keep-summarizing` if needed, project file checks are limited to referenced files, compact executor-result fields are validated by applicability rather than fixed Markdown sections, validation/blocker/task-fit/repository evidence is present when applicable, applicable CodeGraph evidence is present and consistent or carries an accepted inapplicable/fallback reason, delegated work carries `delegation_evidence` with `visible_reference` when available and `internal_spawn_used_for_task_delegation: false`, active orchestration handoff input is not required, failures create a repair specification instead of modifying implementation files, structural updates invoke the delegate-return-resume protocol, delegation returns written or updated paths or an evidence-backed no-write rationale plus index rebuild status, specification-included violations are closed only on passing unblocked review with lifecycle evidence, material specification-carried unsettled evidence is settled before archive, allowed commit, applicable CodeGraph sync, and project metadata update gates are complete or explicitly not applicable before archive, success/archive is allowed only for `Knowledge update disposition: completed` or `Knowledge update disposition: not-needed`, unavailable or incomplete delegation blocks archive with an actionable `ks-extract-valuable-points` next action, review may invoke an approved `ks-*` owner but must not write durable knowledge directly, indexes are refreshed, no files are deleted, and no artifact is written under `.work-bundle/knowledge/`.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-knowledge-gateway`: `rules/orchestration/orch-knowledge-gateway.md`
- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`
- `orch-review-completion`: `rules/orchestration/orch-review-completion.md`

## Rule Loading (mandatory)

Before substantive review work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive orchestration work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or directive summaries as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress orchestration task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Boundary

Platform write boundary and durable-knowledge prohibition: follow `orch-orchestration-boundary` (`rules/orchestration/orch-orchestration-boundary.md`). You may invoke, schedule, or hand off to an approved `ks-*` owner and consume its result per that rule.

> **Deprecation:** The role-context subsystem is deprecated; see spec §0.9 in `spec-process-orch-skill-rule-boundary-optimization-20260611`. Do not invoke it from orch skills.
