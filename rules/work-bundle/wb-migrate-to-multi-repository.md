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

Require dry-run-first, source-preserving, recoverable migration from a supported single-repository workspace to a supported multi-repository workspace.

## Must

- Invoke `wb-migrate-to-multi-repository` with explicit source `project_root`, target `workspace_root`, workspace slug, repository identity/name, working branch, and base ref.
- Classify legacy topology from both workspace metadata and the bootstrap-resolved registry. Permit in-place metadata migration only when the evidence is unambiguously single-repository; route multiple repositories here and block identity disagreement or proposal drift.
- Run inspect and dry-run proposal before explicit apply and report source repository and nested `.work-bundle` Git state separately. Require the exact proposal-derived accepted-baseline ID before applying either dirty state.
- Preserve source repository, branch, worktree, `.work-bundle`, registry entry, script utilities, and credential store unchanged until target verification passes.
- Copy and verify WorkBundle state and indexed workspace utilities without following unsafe symlinks or treating transient caches as authority.
- Create an empty protected target credential store; require separate secure local transfer or recreation and never copy credential content automatically.
- Provision a workspace-local Git control store and named member worktree, then publish registry and metadata only after target verification.
- Verify SessionStart discovery, member preflight, workspace-local Git control, staged metadata/registry identities, resources, and source preservation before publishing any active state.
- Publish metadata v3 and the bootstrap-resolved locator registry atomically or recoverably after final verification, with before/after identity and digest evidence.
- Treat a provisioned checkout in `verified` state as internal and incomplete. A public `provision-member` success requires metadata and registry publication; matching verified retries resume publication and published retries replay without writes.
- Record partial failure outside disposable owned paths as a redacted recoverable transaction supporting idempotent retry or rollback of migration-owned target paths only.
- Return an already published retry from the persisted complete result with the same transaction identity/context and no metadata, registry, target, or recovery-record write.

## Must Not

- Do not commit, clean, stash, reset, delete, deregister, relocate, or silently change the source workspace or repository.
- Do not create a direct linked worktree whose Git common directory remains outside `workspace_root`.
- Do not publish a false active target registry entry or reuse conflicting paths or branches.
- Do not let `migrate-project --force` override topology classification or report public provisioning success while metadata or registry publication is pending.
- Do not delete the recovery record when rolling back transaction-owned target paths.
- Do not copy, print, index, delegate, or archive credential material.

## Validation

- Verify source preservation, copy inventory/digests, script-index consistency, credential exclusion, AGENTS merge, and target resource protection.
- Verify member path and absolute Git common directory are within `workspace_root`, branch/base/HEAD evidence matches, and metadata/registry converge.
- Verify SessionStart discovery and per-member preflight from nested target paths.
- Verify multi-source legacy input routes to this workflow and public member results never combine `status: passed` with pending publication.
- Verify failure recovery touches only transaction-owned target paths and leaves source authority active.

## On Violation

Stop migration publication, preserve the source unchanged, record a redacted recoverable failure, and permit only idempotent retry or explicit rollback of validated migration-owned target paths.
