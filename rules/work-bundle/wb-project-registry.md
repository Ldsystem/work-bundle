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

Ensure project registration and lookup preserve the versioned authority split between portable metadata, device-local bindings, and registry locators.

## Must

- Resolve the project registry path from `$work_bundle_config_root/bootstrap.yaml` field `project_registry`.
- Use only the bootstrap-resolved `project_registry` path to create workspace slugs, register workspace/repository locators, and read or publish metadata-v4 `device_bindings`.
- Treat registry project entries as locator authority for workspace slug/root, knowledge root, aliases, and stable repository origin `id`, `origin_path`, `remote`, and Git capability.
- Treat metadata-v4 `device_bindings` in that same registry as device-local authority for materialized workspace/control-plane paths, member `project_root` paths, checkout kinds, and checkout/control-plane observations.
- Treat metadata-v4 `$workspace_root/.work-bundle/project.yaml` as portable project/topology authority and forbid device-local paths or observations there.
- Preserve metadata-v3 `$workspace_root/.work-bundle/project.yaml` working-state authority only for explicit v3 reads and migrations.
- Register every initialized single- or multi-repository workspace to `projects.yaml` under an explicit new or existing workspace slug, and create or update the corresponding workspace metadata.
- When changing portable topology, update its durable authorities through an atomic or recoverable workflow; when attaching metadata v4, publish only the device-local binding after all materializations validate.
- Describe registry, device-binding, metadata-v4 portable, and metadata-v3 compatibility roles without collapsing them into one working-state model.
- Preserve metadata v2 locator entries as compatibility input during explicit migration, preserve unknown fields, and publish v3 origin/member separation only after target verification.

## Must Not

- Do not infer project locations from recent conversation when registry access is required.
- Do not register a project without an explicit workspace slug decision.
- Do not store project registry state under `work_bundle_root` or `project_root`.
- Do not store metadata-v4 device-local paths or observations outside `device_bindings` or inside portable `project.yaml`.
- Do not write any registry data to an independently hardcoded default when bootstrap declares another `project_registry` path.
- Do not require portable metadata mutation when publishing or refreshing only a metadata-v4 device binding.
- Do not apply metadata-v3 local working-state ownership to metadata v4.

## Validation

- Inspect the command or workflow and verify registry paths are resolved through bootstrap.
- Verify all locator and device-binding IO uses only the bootstrap-resolved `project_registry`.
- Verify initialized projects have both a registry entry and a matching `$project_root/.work-bundle/project.yaml`.
- Verify metadata-v4 portable repositories remain path-free while matching device bindings contain local materialization and observation fields.
- Verify metadata-v3 local fields remain accepted only in explicit v3 compatibility reads and migrations.

## On Violation

Stop project registration or lookup and report the missing bootstrap-resolved registry, missing locator or device binding, misplaced versioned authority field, unsafe partial publication, or missing slug decision.
