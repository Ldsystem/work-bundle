---
name: wb-initialize-project
description: Initialize, validate, doctor, or migrate single- and multi-repository WorkBundle workspaces through the current metadata-v4 control-plane commands. Use for workspace creation, attachment, registry/device binding, or explicit historical metadata migration.
---

# Initialize a WorkBundle Workspace

Use the public `scripts/wb.py` entrypoint. It owns its maintained YAML and JSON Schema runtime; do not substitute release CI or direct module imports for the supported command.

## Current authority

- Resolve `work_bundle_config_root` as `~/.work-bundle/` and read its `bootstrap.yaml` before locating registries or toolkit assets.
- Treat `$workspace_root/.work-bundle/project.yaml` metadata v4 as portable project/topology authority for identity, repository topology, canonical remote, branch policy, and operation policy.
- Treat the matching `device_bindings[workspace_id]` in the bootstrap-resolved project registry as local workspace/member path and observation authority.
- Keep `work_bundle_config_root`, `workspace_root`, and each selected member `project_root` distinct. A member selector must join to the selected workspace by workspace and repository IDs; never infer authority from a locator path.
- Use `script/index.yaml` for workspace utility discovery in both repository modes. Discovery does not authorize execution.
- Discover project rules from `$workspace_root/.work-bundle/rules/index.yaml`.
- The root `rules/index.yaml` is legacy-only, so preserve it as a legacy artifact only during explicit migration.
- Read enabled rule indexes first, then load every applicable rule body in full according to its metadata.
- Never open or ingest `credentials/credentials.yaml`; validate only its protected structure and permissions.

## Public operations

Create current workspaces with:

```text
python3 scripts/wb.py init-workspace <workspace-root> --slug <slug> --repository <id=remote> --mode <single-repository|multi-repository> (--dry-run|--apply)
```

Attach local materializations with `attach-workspace`, inspect with `show-project`, validate with `validate-project`, and diagnose with `doctor-workspace` or `doctor-project`. These operations consume the same schema-owned metadata-v4 and device-binding join.

`init-project` and `initialize-project` are retired and return `WB_CURRENT_INIT_COMMAND_RETIRED`; they must not create metadata v3 or act as producer aliases.

Historical metadata v2/v3 is migration input only:

- Use `migrate-control-plane <workspace-root> --dry-run` to produce one proposal for a single workspace.
- Apply only with the exact accepted proposal ID; publish validated metadata v4 directly without installing an intermediate current v3.
- Use `migrate-registered-projects` for the registry-wide v2/v3 path.
- Preserve historical bytes/unknown portable fields where the migration contract allows them. Unsupported versions or ambiguous topology fail before mutation.

Agents do not edit the project registry directly and do not change an external repository's Git config. Supply semantic inputs such as `--repository <id=remote>` to the owning public transaction.

## Mutation boundary

Validate schemas, workspace/member containment, branch policy, canonical remotes, device-binding joins, and effect-bearing inputs before writes. Publish project metadata and registry/device bindings atomically or through the existing recoverable transaction. Preserve unrelated registry entries, templates, rules, knowledge, orchestration artifacts, and user-authored AGENTS content.

In both workspace modes, create or preserve `$workspace_root/script/index.yaml`.
In both workspace modes, create or preserve `$workspace_root/credentials/credentials.yaml`; never read credential values.

Scripts report structural facts and failures only. The acting agent determines whether the created or migrated workspace fulfills the user's purpose; doctor success is not semantic acceptance.

## Self-check

- Did ordinary creation emit only schema-valid metadata v4 and a matching device binding, with no local path or observation in portable metadata?
- Are v2/v3 accepted only by explicit migration commands, with retired creation spellings refusing rather than writing legacy state?
- Did config, workspace, and selected member roots remain distinct, and did every member join by stable IDs without locator/path fallback?
- Were maintained YAML/schema validation and all effect-bearing checks completed before atomic or recoverable mutation?
- Did I preserve unrelated files and avoid credential values, Git staging/commit, utility execution, and semantic acceptance claims?

## Runtime rules

- `wb-project-context-preflight`
- `wb-project-registry`
- `rule-work-bundle-security-exclusion`
