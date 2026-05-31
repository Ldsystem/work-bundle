---
name: review-plan
description: 'Review an implemented plan against its specification, handoffs, and project files; create a repair specification on failure or archive completed artifacts on success.'
---

# Review Plan

Review `${input:ReviewTarget}` after execution. Use this directive for final verification, repair-spec creation, and archival of completed orchestration artifacts.

For v3 knowledge, validation-backed promotion requires front matter evidence in durable notes when a note is promoted to `implemented` or when `current` is promoted from `implemented`. When review needs durable knowledge, use the `implementation_plan` retrieval policy through `keep-summarizing` gateway mode. Review may recommend durable knowledge extraction through `keep-summarizing`, but it must not silently write durable knowledge or treat candidate/background retrieval as implemented authority.

Review output must include a final line in this exact form: `Knowledge update disposition: completed|not-needed|blocked|required`.

## Context Boundary

Allowed:

- related active specification under `.work-bundle/orchestration/spec/active/`;
- related active plan, phase, and task files under `.work-bundle/orchestration/plan/active/`;
- related executor and orchestration handoffs under `.work-bundle/orchestration/handoff/`;
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
- orchestration handoffs that claim review, blockers, or continuation state;
- relevant project files referenced by the resolved artifacts.

Stop if the plan or source specification cannot be resolved.

## Review Procedure

Validate:

1. specification requirements, constraints, interfaces, and acceptance criteria are represented in the plan;
2. plan phases and tasks cover the specification without unsupported scope expansion;
3. executor handoffs exist for completed tasks and include files changed, symbols changed, validation, deviations, unresolved issues, and next action;
4. phase and plan handoffs exist when those scopes are marked `Completed`;
5. project files reflect the implementation claimed by the handoffs;
6. validation evidence satisfies the task, phase, plan, and specification criteria;
7. statuses are coherent across task files, phase task indexes, root plan phase indexes, handoff statuses, and indexes;
8. no required artifact is missing, stale, contradictory, or under `.work-bundle/knowledge/`;
9. the source specification `Knowledge Base Update` section is reflected in the final review state, including expected durable conclusions, evidence, and follow-up path;
10. the final knowledge-update disposition is one of `completed`, `not-needed`, `blocked`, or `required`, with evidence for that outcome.

## Failure Path

If any review check fails:

- do not archive artifacts;
- create a new active repair specification under `.work-bundle/orchestration/spec/active/`;
- include discrepancies, evidence, affected spec/plan/handoff/project files, severity, required fixes, and acceptance criteria;
- link the repair specification to the reviewed plan and related handoffs;
- report the repair specification path and the next `create-implementation-plan` or `execute-plan` action.
- if the knowledge update disposition remains `required`, report that archival is blocked and instruct the agent to use `ks-extract-valuable-points` for mixed implementation/review evidence or `ks-breakdown-design` when the evidence source is a design file.
- if the knowledge update disposition is `blocked` without an actionable blocker path, treat the review as failed and require repair rather than archive.

The repair specification must be actionable without raw chat history.

## Success Path

If all review checks pass and the knowledge update disposition is `completed` or `not-needed`:

- mark related executor and orchestration handoffs `reviewed`, then archive them;
- archive the related source specification;
- archive the related root plan file, phase files, and task files;
- refresh spec, plan, and handoff indexes;
- report archived paths and state that the plan is review-complete.

Archival means moving files from `active/` to the corresponding `archived/` directory. Do not delete files.

Do not archive when the knowledge update disposition is `required` or when it is `blocked` without an actionable blocker path. Those outcomes are blocked or failed review states, not success states.

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

Confirm reviewed artifacts match the requested plan, durable knowledge was accessed only through `keep-summarizing` if needed, project file checks are limited to referenced files, failures create a repair specification instead of modifying implementation files, success/archive is allowed only for `Knowledge update disposition: completed` or `Knowledge update disposition: not-needed`, unresolved `required` dispositions route to `ks-extract-valuable-points` for mixed evidence or `ks-breakdown-design` for design files, review may recommend keep-summarizing follow-up but must not write durable knowledge directly, indexes are refreshed, no files are deleted, and no artifact is written under `.work-bundle/knowledge/`.
