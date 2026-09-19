---
id: wb-migrate-to-multi-repository
applies_when:
  - a user asks to migrate a current single-repository WorkBundle project into a multi-repository workspace
  - an approved migration workflow inspects, dry-runs, applies, retries, or rolls back single-to-multi topology migration
enforcement: must
load: conditional
requires:
  - wb-project-context-preflight
  - wb-project-registry
  - rule-work-bundle-security-exclusion
---

# Migrate To Multi-Repository Workspace

## Purpose

Route single-to-multi requests through current metadata-v4 transactions without reviving the retired metadata-v3 topology producer.

## Must

- Treat `migrate-to-multi-repository` as a retired typed refusal and follow its v4 guidance.
- For a new multi-repository workspace, use `init-workspace --mode multi-repository`; validate its portable metadata and matching device bindings before publication.
- For metadata v2/v3 input, use `migrate-control-plane` or `migrate-registered-projects` and require the exact accepted proposal or plan identity before apply.
- For an existing metadata-v4 workspace, use the proposal-bound `add-workspace-member` transaction.
- Preserve source repositories and unrelated workspace files, and keep portable topology separate from device-local paths and observations.
- Publish metadata v4 directly and validate the portable/device-binding join by stable workspace and repository IDs.

## Must Not

- Do not invoke the historical topology migration module or publish metadata v3 as a current state.
- Do not use `provision-member` or `cleanup-member`; both are retired v3-mutating routes.
- Do not infer a device binding from a repository locator or permit a member path or Git common directory to escape `workspace_root`.
- Do not commit, clean, stash, reset, delete, deregister, relocate, or silently change a source repository.
- Do not copy, print, index, delegate, or archive credential material.

## Validation

- Verify the selected v4 command, its dry-run/apply identity when applicable, schema-valid metadata v4, matching device bindings, and source preservation.
- Verify legacy v2/v3 input is admitted only by an explicit migration command and no intermediate metadata v3 state is published.
- Verify member and Git common-directory paths remain inside `workspace_root` and observations match live Git state before use.

## On Violation

Stop publication, preserve the source unchanged, and route to the matching v4 initialization, migration, member-add, attach, or doctor command.
