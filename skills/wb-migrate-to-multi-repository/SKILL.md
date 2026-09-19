---
name: wb-migrate-to-multi-repository
description: Route a requested legacy topology migration to the current metadata-v4 workspace creation or explicit historical metadata migration path. The former v3-producing public command is retired.
---

# Route Multi-Repository Migration

Do not run the former `migrate-to-multi-repository` implementation. The public command returns `WB_TOPOLOGY_MIGRATION_COMMAND_RETIRED` because it produced metadata v3, which is no longer a current format.

Choose the current v4 owner from the user's purpose:

- For a new multi-repository workspace, use `init-workspace <workspace-root> --mode multi-repository --slug <slug> --repository <id=remote> ...` with dry-run before apply.
- For an existing workspace whose `.work-bundle/project.yaml` is metadata v2 or v3, use `migrate-control-plane <workspace-root> --dry-run`, then apply only the exact accepted proposal ID.
- For registry-wide historical migration, use `migrate-registered-projects` with its exact accepted plan ID.
- For adding a repository to an existing current workspace, use the v4 `add-workspace-member` proposal/apply transaction.

Preserve source repositories and unrelated workspace files. Never use the historical Python migration module as a public producer, never publish an intermediate metadata v3 document, and never treat a repository locator as a device binding.

## Self-check

- Did the selected command emit or preserve schema-valid metadata v4 only?
- If the input was v2/v3, was it admitted solely through an explicit historical migration command?
- Are portable topology and device-local paths still separated and joined by stable IDs?
- Did I avoid staging, committing, deleting, or mutating source state outside the chosen v4 transaction?

## Runtime rules

- `wb-project-context-preflight`
- `wb-project-registry`
- `rule-work-bundle-security-exclusion`
