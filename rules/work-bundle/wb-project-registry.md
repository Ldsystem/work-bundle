---
id: wb-project-registry
applies_when:
  - task.registers_project
  - task.registers_source_repository
  - task.creates_workspace_slug
  - task.resolves_project_location
  - task.resolves_knowledge_base_location
enforcement: must
load: conditional
requires: []
---

# Project Registry

## Purpose

Ensure project registration and lookup keep the bootstrap-resolved project registry and project-local metadata synchronized according to their separate roles.

## Must

- Resolve the project registry path from `$work_bundle_config_root/bootstrap.yaml` field `project_registry`.
- Use `$work_bundle_config_root/registry/projects.yaml` to create workspace slugs, register projects, and resolve project or knowledge-base locations.
- Treat `$work_bundle_config_root/registry/projects.yaml` as the locator authority: workspace slug, project root, knowledge root, source repository `id`, `path`, `work_dir`, `remote`, and `git_repository`.
- Treat `$project_root/.work-bundle/project.yaml` as the project metadata authority: workspace structure, source repository roles, operation policy, branch baseline, commit baseline, baseline status, and CodeGraph support or sync state.
- Register every initialized project to `projects.yaml` as an individual workspace slug or an existing workspace slug, and create or update the corresponding `$project_root/.work-bundle/project.yaml`.
- When registering a new source repository to a workspace, update both `projects.yaml` and `$project_root/.work-bundle/project.yaml` in the same workflow.
- Include a short description of registry and project metadata roles in project metadata, so agents know the registry is a locator and project metadata is the working-state authority.
- Source `source_repositories[]` entries from the project registry during migration or initialization, then enrich the corresponding project metadata entries with branch, commit, baseline, operation policy, and CodeGraph state.

## Must Not

- Do not infer project locations from recent conversation when registry access is required.
- Do not register a project without an explicit workspace slug decision.
- Do not store project registry state under `work_bundle_root` or `project_root`.
- Do not store branch baseline, commit baseline, operation policy, source repository roles, or CodeGraph sync state in `projects.yaml`.
- Do not update `projects.yaml` for a project or source repository registration without also updating the matching `$project_root/.work-bundle/project.yaml`.
- Do not update `$project_root/.work-bundle/project.yaml` with a new source repository without also updating the bootstrap-resolved `projects.yaml` locator entry.

## Validation

- Inspect the command or workflow and verify registry paths are resolved through bootstrap.
- Verify project registration writes only to the bootstrap-resolved `projects.yaml`.
- Verify initialized projects have both a registry entry and a matching `$project_root/.work-bundle/project.yaml`.
- Verify newly registered source repositories appear in both the registry locator and project metadata working-state sections.
- Verify project metadata includes short role descriptions for the registry and project metadata responsibilities.
- Verify `projects.yaml` contains locator fields only and does not own branch, commit, operation policy, source repository roles, or CodeGraph sync state.

## On Violation

Stop project registration or lookup and report the missing registry path, missing registry entry, missing project metadata update, missing source repository mirror, misplaced working-state field, or missing slug decision.
