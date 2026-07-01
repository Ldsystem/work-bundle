---
id: wb-violation-evidence
applies_when:
  - wb-violation-evaluation classifies an observed conflict, violation, error, failed validation, contradictory workflow behavior, user interruption, or user correction as work-bundle-scoped or mixed
  - visible first-observed evidence must be stored after evaluation identifies a WorkBundle skill, rule, script, workflow, orchestration contract, handoff contract, or toolkit execution surface deviation
enforcement: must
load: always
requires:
  - wb-violation-evaluation
---

# Violation Evidence

## Purpose

Preserve first-observed work-bundle process, rule, skill, workflow, script, orchestration, or handoff contract deviations under the global violation store after evaluation classifies the finding as `work-bundle-scoped` or `mixed`, without turning the active task into root-cause repair.

## Must

- Record a violation evidence file when `wb-violation-evaluation` classifies the first-observed finding as `work-bundle-scoped` or `mixed`.
- Record only the minimal first-observed evidence needed to preserve the WorkBundle-scoped or mixed deviation after evaluation.
- Keep evidence narrow to the deviation, occurrence condition, visible first evidence artifacts, current status, action taken when any, and severity.
- Record only files, artifacts, UI output, terminal output, or runtime surfaces already visible in the active task context at the moment the work-bundle violation is observed.
- Use `$work_bundle_config_root/violation/active/` for unresolved evidence and `$work_bundle_config_root/violation/archived/` for dismissed or completed evidence.
- Use evidence filenames shaped as `evidence-<yyyyMMdd>-<short-description>.yaml`.
- Use the `violation-ensure-store`, `violation-create-evidence`, `violation-build-index`, `violation-write-index`, and `violation-archive-evidence` script entry points when writing, indexing, or moving evidence files is required.
- Treat project-scoped findings from `wb-violation-evaluation` as blockers reported to the user rather than work-bundle violation records.
- Treat undetermined findings that affect authority, target scope, validation, or continuation as resolution blockers until evaluation can classify them.

## Must Not

- Do not record project business logic, project implementation, project spec or plan execution, or durable project-knowledge semantic deviations in the work-bundle violation store.
- Do not expand evidence capture into evaluation, root-cause investigation, or exhaustive workflow-chain tracing.
- Do not perform additional file search, repository browsing, historical tracing, or contract exploration solely to find more evidence when the already-visible artifact is sufficient to record the violation.
- Do not delay or widen plan execution to enrich a violation record.
- Do not store violation evidence under project roots or `.work-bundle/knowledge/`.
- Do not use executor-result forbidden advice fields as the violation recording surface.
- Do not silently continue from a work-bundle violation that makes the active execution unsafe, unauthoritative, or impossible to verify.

## Validation

- Confirm every recorded violation was classified by `wb-violation-evaluation` as `work-bundle-scoped` or `mixed` and cites only visible first evidence artifacts or runtime surfaces.
- Confirm the agent did not perform further exploration solely to enrich the violation evidence record.
- Confirm project-scope deviations are reported as blockers and are not written to the violation store.
- Confirm undetermined findings that affect authority, target scope, validation, or continuation are blocked for resolution rather than written as evidence.
- Confirm evidence path, status, action, and severity satisfy the violation evidence contract.
- Confirm the violation index is rebuilt or explicitly left for `violation-write-index` after evidence changes.

## On Violation

Stop the unsafe action when the deviation affects authority, target scope, validation, or continuation. Otherwise record the minimal evidence file, rebuild or request index refresh, and resume only from the loaded work-bundle contract that remains authoritative.
