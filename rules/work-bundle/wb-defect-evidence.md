---
id: wb-defect-evidence
applies_when:
  - the Work Bundle rule is visible in AGENTS.md and any conflict, confliction, violation, contradiction, or user correction occurs
  - the Work Bundle rule is visible in AGENTS.md and the session needs a visible entry point for defect evaluation and first-observed evidence routing
enforcement: must
load: always
requires: []
---

# Defect Evidence

## Purpose

Keep the WorkBundle defect workflow visible whenever the Work Bundle rule is visible in `AGENTS.md`, and preserve first-observed work-bundle process, rule, skill, workflow, script, orchestration, or handoff contract deviations only after evaluation confirms the finding is `work-bundle-scoped` or `mixed`.

## Must

- Treat any conflict, confliction, violation, contradiction, or user correction as a `wb-defect-evidence` trigger when the Work Bundle rule is visible in `AGENTS.md`.
- When a trigger appears, immediately call `wb-defect-evaluation` to classify whether the finding is `work-bundle-scoped`, `project-scoped`, `mixed`, or `undetermined`.
- Exit the defect evidence workflow without recording evidence when `wb-defect-evaluation` confirms the finding is not WorkBundle-related and does not affect authority, target scope, validation, or continuation.
- Exit the defect evidence workflow without recording a new evidence file when `wb-defect-evaluation` returns `same-scope specification-owned` handling for exact current WorkBundle specification work.
- When `same-scope specification-owned` handling applies, rely on the active specification source context, Open Questions, or review evidence to carry the issue and its settlement path.
- Record a defect evidence file only when `wb-defect-evaluation` classifies the first-observed finding as `work-bundle-scoped` or `mixed`.
- Record only the minimal first-observed evidence needed to preserve the WorkBundle-scoped or mixed deviation after evaluation.
- Keep evidence narrow to the deviation, occurrence condition, visible first evidence artifacts, current status, action taken when any, and severity.
- Record only files, artifacts, UI output, terminal output, or runtime surfaces already visible in the active task context at the moment the work-bundle defect candidate is observed.
- Use `$work_bundle_config_root/defect/active/` for unresolved evidence and `$work_bundle_config_root/defect/archived/` for dismissed or completed evidence.
- Use evidence filenames shaped as `evidence-<yyyyMMdd>-<short-description>.yaml`.
- Use `defect-migrate-store` explicitly when the legacy store remains; the other defect commands must fail before creating or reading the destination until migration completes.
- Use the `defect-ensure-store`, `defect-create-evidence`, `defect-build-index`, `defect-write-index`, and `defect-archive-evidence` script entry points when writing, indexing, or moving evidence files is required.
- Keep the evaluation compact and stop once visible WorkBundle relatedness is established.
- Treat project-scoped findings from `wb-defect-evaluation` as blockers reported to the user rather than work-bundle defect records.
- Treat undetermined findings that affect authority, target scope, validation, or continuation as resolution blockers until evaluation can classify them.

## Must Not

- Do not record project business logic, project implementation, project spec or plan execution, or durable project-knowledge semantic deviations in the work-bundle defect store.
- Do not record a separate defect evidence file for exact current WorkBundle specification-owned work when evaluation explicitly says evidence persistence is not required.
- Do not wait for a user to explicitly request defect recording before considering the defect workflow.
- Do not expand evidence capture into evaluation, root-cause investigation, or exhaustive workflow-chain tracing.
- Do not perform additional file search, repository browsing, historical tracing, or contract exploration solely to find more evidence when the already-visible artifact is sufficient to record the defect.
- Do not delay or widen plan execution to enrich a defect record.
- Do not store defect evidence under project roots or `.work-bundle/knowledge/`.
- Do not make a non-migration defect command migrate, merge, or initialize beside legacy authority.
- Do not use executor-result forbidden advice fields as the defect recording surface.
- Do not silently continue from a work-bundle defect that makes the active execution unsafe, unauthoritative, or impossible to verify.

## Validation

- Confirm `wb-defect-evidence` is loaded as the always-visible entry point for conflict, confliction, violation, contradiction, and user-correction signals when the Work Bundle rule is visible in `AGENTS.md`.
- Confirm possible defect signals are routed first from `wb-defect-evidence` to `wb-defect-evaluation`.
- Confirm `same-scope specification-owned` evaluation results do not create new defect evidence and are carried by the active specification or review evidence instead.
- Confirm every recorded defect was classified by `wb-defect-evaluation` as `work-bundle-scoped` or `mixed` and cites only visible first evidence artifacts or runtime surfaces.
- Confirm the agent did not perform further exploration solely to enrich the defect evidence record.
- Confirm project-scope deviations are reported as blockers and are not written to the defect store.
- Confirm undetermined findings that affect authority, target scope, validation, or continuation are blocked for resolution rather than written as evidence.
- Confirm evidence path, status, action, and severity satisfy the defect evidence contract.
- Confirm legacy state routes to explicit `defect-migrate-store` and every other defect command fails before destination initialization.
- Confirm the defect index is rebuilt or explicitly left for `defect-write-index` after evidence changes.

## On Violation

Stop unsafe continuation, call `wb-defect-evaluation`, and either record minimal evidence for `work-bundle-scoped` or `mixed` findings, exit without persistence for `same-scope specification-owned` handling, report or exit for non-WorkBundle findings, or block when `undetermined` affects authority, target scope, validation, or continuation.
