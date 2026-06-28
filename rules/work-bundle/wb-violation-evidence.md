---
id: wb-violation-evidence
applies_when:
  - agent observes a contradiction between work-bundle rules, skills, scripts, orchestration contracts, handoff contracts, or workflow references
  - user interrupts a work-bundle skill execution and explicitly corrects toolkit process behavior
  - user explicitly requests a work-bundle skill and provides appendix restrictions or corrections that may require skill or rule enrichment
  - a work-bundle document or orchestration artifact violates a loaded work-bundle rule or skill contract
enforcement: must
load: always
requires: []
---

# Violation Evidence

## Purpose

Preserve first-observed work-bundle process, rule, skill, workflow, script, orchestration, or handoff contract deviations under the global violation store without turning the active task into root-cause repair.

## Must

- Record a violation evidence file when a work-bundle rule, skill, script, workflow, orchestration contract, handoff contract, or toolkit execution surface contradicts another loaded work-bundle contract.
- Record a violation evidence file when the user interrupts work-bundle skill execution and explicitly corrects toolkit process behavior.
- Record a violation evidence file when the user provides appendix restrictions or corrections while explicitly requesting a work-bundle skill and those restrictions may require later skill or rule enrichment.
- Keep evidence narrow to the deviation, occurrence condition, visible first evidence artifacts, current status, action taken when any, and severity.
- Record only files, artifacts, UI output, terminal output, or runtime surfaces already visible in the active task context at the moment the work-bundle violation is observed.
- Use `$work_bundle_config_root/violation/active/` for unresolved evidence and `$work_bundle_config_root/violation/archived/` for dismissed or completed evidence.
- Use evidence filenames shaped as `evidence-<yyyyMMdd>-<short-description>.yaml`.
- Use the `violation-ensure-store`, `violation-create-evidence`, `violation-build-index`, `violation-write-index`, and `violation-archive-evidence` script entry points when writing, indexing, or moving evidence files is required.
- Treat project-scope deviations as blockers reported to the user rather than work-bundle violation records.

## Must Not

- Do not record project business logic, project implementation, project spec or plan execution, or durable project-knowledge semantic deviations in the work-bundle violation store.
- Do not expand evidence capture into root-cause investigation unless the active task explicitly requests work-bundle contract investigation or repair.
- Do not perform additional file search, repository browsing, historical tracing, or contract exploration solely to find more evidence when the already-visible artifact is sufficient to record the violation.
- Do not delay or widen plan execution to enrich a violation record.
- Do not store violation evidence under project roots or `.work-bundle/knowledge/`.
- Do not use executor-result forbidden advice fields as the violation recording surface.
- Do not silently continue from a work-bundle violation that makes the active execution unsafe, unauthoritative, or impossible to verify.

## Validation

- Confirm every recorded violation is work-bundle scoped and cites only visible first evidence artifacts or runtime surfaces.
- Confirm the agent did not perform further exploration solely to enrich the violation evidence record.
- Confirm project-scope deviations are reported as blockers and are not written to the violation store.
- Confirm evidence path, status, action, and severity satisfy the violation evidence contract.
- Confirm the violation index is rebuilt or explicitly left for `violation-write-index` after evidence changes.

## On Violation

Stop the unsafe action when the deviation affects authority, target scope, validation, or continuation. Otherwise record the minimal evidence file, rebuild or request index refresh, and resume only from the loaded work-bundle contract that remains authoritative.
