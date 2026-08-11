---
name: wb-migrate-to-multi-repository
description: Inspect, dry-run, apply, verify, retry, or roll back a source-preserving migration from a single-repository WorkBundle project to a multi-repository workspace. Use when the user explicitly requests this topology migration.
---

# Migrate To Multi-Repository Workspace

Load `rules/work-bundle/wb-migrate-to-multi-repository.md`, project preflight/registry rules, and security exclusion. Resolve explicit source authority `project_root`, target `workspace_root`, workspace slug, repository ID/name, working branch, base ref, optional primary Git `origin`, and any additional origin locators. When the authority root is not Git-backed, `--origin` is required and must select one of its declared reusable Git source repositories.

Always run inspect and dry-run before requesting explicit apply authority. Report the source repository and nested `.work-bundle` Git states separately. When either is dirty, pass the exact accepted-baseline ID returned by the proposal; never synthesize or bypass it. Never clean, stash, reset, commit, delete, relocate, or deregister source state.

Treat multiple legacy repository locators as a routing signal, not proof that a valid multi-repository workspace already exists. The in-place `migrate-project` command must stop and route such evidence here; only this workflow may create workspace-local control stores and managed worktrees.

On apply, copy and verify `.work-bundle`, preserve nested Git history and unknown files, copy indexed `script/`, merge managed AGENTS content, exclude credential content, create an empty protected credential store, and provision a workspace-local control store plus named worktree. Publish registry authority only after all target verification passes.

Verify SessionStart discovery, member preflight, workspace-local Git control, staged metadata/registry identities, resources, and source preservation before publication. Publish metadata v3 and the bootstrap-resolved locator registry through one atomic-or-recoverable transaction only after every check passes. Keep built-in skills outside the external skill registry.

On failure, retain a redacted transaction record outside disposable owned paths. Permit only idempotent retry with the same accepted baseline or rollback of transaction-owned target paths; restore partial publication without leaving a false active member. For an already published transaction, replay the persisted complete result and stable transaction evidence without writing or republishing. Never expose credential contents or sensitive paths.

For later `provision-member` operations, checkout verification is internal. Public success requires the new member in workspace metadata and its origin in the bootstrap-resolved registry through the same recoverable publication boundary. A matching verified-but-unpublished transaction resumes; it is not an unrelated target collision.

An older verified checkout may predate recovery records. Resume it only after exact workspace-local control, origin, repository ID, branch, and base-HEAD verification. Do not delete it through cleanup unless a recovery record proves it is unpublished and transaction-owned.
