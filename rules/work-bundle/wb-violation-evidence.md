---
id: wb-violation-evidence
applies_when:
  - the Work Bundle rule is visible in AGENTS.md and any conflict, confliction, violation, contradiction, or user correction occurs
  - the Work Bundle rule is visible in AGENTS.md and the session needs a visible entry point for violation evaluation and first-observed evidence routing
enforcement: must
load: always
requires: []
---

# Violation Evidence

## Purpose

Keep the WorkBundle violation workflow visible whenever the Work Bundle rule is visible in `AGENTS.md`, and preserve first-observed work-bundle process, rule, skill, workflow, script, orchestration, or handoff contract deviations only after evaluation confirms the finding is `work-bundle-scoped` or `mixed`.

## Must

- Treat any conflict, confliction, violation, contradiction, or user correction as a `wb-violation-evidence` trigger when the Work Bundle rule is visible in `AGENTS.md`.
- When a trigger appears, immediately call `wb-violation-evaluation` to classify whether the finding is `work-bundle-scoped`, `project-scoped`, `mixed`, or `undetermined`.
- Exit the violation evidence workflow without recording evidence when `wb-violation-evaluation` confirms the finding is not WorkBundle-related and does not affect authority, target scope, validation, or continuation.
- Record a violation evidence file only when `wb-violation-evaluation` classifies the first-observed finding as `work-bundle-scoped` or `mixed`.
- Record only the minimal first-observed evidence needed to preserve the WorkBundle-scoped or mixed deviation after evaluation.
- Keep evidence narrow to the deviation, occurrence condition, visible first evidence artifacts, current status, action taken when any, and severity.
- Record only files, artifacts, UI output, terminal output, or runtime surfaces already visible in the active task context at the moment the work-bundle violation is observed.
- Use `$work_bundle_config_root/violation/active/` for unresolved evidence and `$work_bundle_config_root/violation/archived/` for dismissed or completed evidence.
- Use evidence filenames shaped as `evidence-<yyyyMMdd>-<short-description>.yaml`.
- Use the `violation-ensure-store`, `violation-create-evidence`, `violation-build-index`, `violation-write-index`, and `violation-archive-evidence` script entry points when writing, indexing, or moving evidence files is required.
- Keep the evaluation compact and stop once visible WorkBundle relatedness is established.
- Treat project-scoped findings from `wb-violation-evaluation` as blockers reported to the user rather than work-bundle violation records.
- Treat undetermined findings that affect authority, target scope, validation, or continuation as resolution blockers until evaluation can classify them.

## Must Not

- Do not record project business logic, project implementation, project spec or plan execution, or durable project-knowledge semantic deviations in the work-bundle violation store.
- Do not wait for a user to explicitly request violation recording before considering the violation workflow.
- Do not expand evidence capture into evaluation, root-cause investigation, or exhaustive workflow-chain tracing.
- Do not perform additional file search, repository browsing, historical tracing, or contract exploration solely to find more evidence when the already-visible artifact is sufficient to record the violation.
- Do not delay or widen plan execution to enrich a violation record.
- Do not store violation evidence under project roots or `.work-bundle/knowledge/`.
- Do not use executor-result forbidden advice fields as the violation recording surface.
- Do not silently continue from a work-bundle violation that makes the active execution unsafe, unauthoritative, or impossible to verify.

## Validation

- Confirm `wb-violation-evidence` is loaded as the always-visible entry point for conflict, confliction, violation, contradiction, and user-correction signals when the Work Bundle rule is visible in `AGENTS.md`.
- Confirm possible violation signals are routed first from `wb-violation-evidence` to `wb-violation-evaluation`.
- Confirm every recorded violation was classified by `wb-violation-evaluation` as `work-bundle-scoped` or `mixed` and cites only visible first evidence artifacts or runtime surfaces.
- Confirm the agent did not perform further exploration solely to enrich the violation evidence record.
- Confirm project-scope deviations are reported as blockers and are not written to the violation store.
- Confirm undetermined findings that affect authority, target scope, validation, or continuation are blocked for resolution rather than written as evidence.
- Confirm evidence path, status, action, and severity satisfy the violation evidence contract.
- Confirm the violation index is rebuilt or explicitly left for `violation-write-index` after evidence changes.

## On Violation

Stop unsafe continuation, call `wb-violation-evaluation`, and either record minimal evidence for `work-bundle-scoped` or `mixed` findings, report or exit for non-WorkBundle findings, or block when `undetermined` affects authority, target scope, validation, or continuation.
