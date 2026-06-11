---
id: wb-project-registry
applies_when:
  - task.registers_project
  - task.creates_workspace_slug
  - task.resolves_project_location
  - task.resolves_knowledge_base_location
enforcement: must
load: conditional
requires: []
---

# Project Registry

## Purpose

Ensure project registration and lookup use the bootstrap-resolved project registry instead of conversation memory or project-local state.

## Must

- Resolve the project registry path from `$work_bundle_config_root/bootstrap.yaml` field `project_registry`.
- Use the project registry to create workspace slugs, register projects, and resolve project or knowledge-base locations.
- Register every initialized project to `projects.yaml` as an individual workspace slug or an existing workspace slug.

## Must Not

- Do not infer project locations from recent conversation when registry access is required.
- Do not register a project without an explicit workspace slug decision.
- Do not store project registry state under `work_bundle_root` or `project_root`.

## Validation

- Inspect the command or workflow and verify registry paths are resolved through bootstrap.
- Verify project registration writes only to the bootstrap-resolved `projects.yaml`.
- Verify initialized projects have a registry entry.

## On Violation

Stop project registration or lookup and report the missing registry path, missing registry entry, or missing slug decision.
