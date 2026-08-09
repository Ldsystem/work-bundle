---
id: wb-project-registry
applies_when:
  - user asks to initialize, register, locate, doctor, or migrate a WorkBundle workspace
  - a workflow creates or updates a workspace slug or repository origin locator
  - a workflow resolves workspace, project, or knowledge locations through the global project registry
enforcement: must
load: conditional
requires: []
---

# Project Registry

## Purpose

Ensure project registration and lookup keep the bootstrap-resolved project registry and project-local metadata synchronized according to their separate roles.

## Must

- Resolve the project registry path from `$work_bundle_config_root/bootstrap.yaml` field `project_registry`.
- Use `$work_bundle_config_root/registry/projects.yaml` to create workspace slugs, register workspaces and repository origins, and resolve workspace or knowledge-base locations.
- Treat `$work_bundle_config_root/registry/projects.yaml` as locator authority for workspace slug/root, knowledge root, aliases, and stable repository origin `id`, `origin_path`, `remote`, and Git capability.
- Treat `$workspace_root/.work-bundle/project.yaml` as working-state authority for workspace mode/resources, member `project_root`, checkout/control-store binding, expected branch/base ref, observed HEAD, lifecycle transaction, operation policy, and CodeGraph state.
- Register every initialized single- or multi-repository workspace to `projects.yaml` under an explicit new or existing workspace slug, and create or update the corresponding workspace metadata.
- When registering a new repository origin or provisioning a member, update registry and workspace metadata through an atomic or recoverable workflow with before/after evidence.
- Include a short description of registry and project metadata roles in project metadata, so agents know the registry is a locator and project metadata is the working-state authority.
- Preserve metadata v2 locator entries as compatibility input during explicit migration, preserve unknown fields, and publish v3 origin/member separation only after target verification.

## Must Not

- Do not infer project locations from recent conversation when registry access is required.
- Do not register a project without an explicit workspace slug decision.
- Do not store project registry state under `work_bundle_root` or `project_root`.
- Do not store member paths, expected branch, observed HEAD, cleanliness, lifecycle transaction, operation policy, or CodeGraph state in `projects.yaml`.
- Do not update `projects.yaml` for a project or source repository registration without also updating the matching `$workspace_root/.work-bundle/project.yaml`.
- Do not update `$workspace_root/.work-bundle/project.yaml` with a new repository origin/member binding without also updating the bootstrap-resolved `projects.yaml` locator entry through the same atomic-or-recoverable transaction.

## Validation

- Inspect the command or workflow and verify registry paths are resolved through bootstrap.
- Verify project registration writes only to the bootstrap-resolved `projects.yaml`.
- Verify initialized projects have both a registry entry and a matching `$project_root/.work-bundle/project.yaml`.
- Verify newly registered source repositories appear in both the registry locator and project metadata working-state sections.
- Verify project metadata includes short role descriptions for the registry and project metadata responsibilities.
- Verify `projects.yaml` contains locator fields only and does not own member checkout state, branch/HEAD observations, cleanliness, lifecycle transaction, operation policy, or CodeGraph state.

## On Violation

Stop project registration or lookup and report the missing registry path, missing registry entry, missing project metadata update, missing source repository mirror, misplaced working-state field, or missing slug decision.
