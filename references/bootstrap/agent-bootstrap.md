# Agent Bootstrap (Compatibility Bridge)

## Authority
Canonical bootstrap authority is global: `~/.work-bundle/bootstrap.yaml`.
This repository file is compatibility guidance, not the primary bootstrap authority.

## Canonical Root Model
- `work-bundle-root`: installed work-bundle source root resolved from `~/.work-bundle/work-bundle-root.yaml`.
- `project-root`: current workspace root.
- `work-bundle-config-root`: `~/.work-bundle/`.

## Root Pointer Contract
Pointer file: `~/.work-bundle/work-bundle-root.yaml`
Required fields:
- `pointer_version` (integer, current `1`)
- `work_bundle_root` (string path)
- `updated_at` (RFC3339 UTC timestamp)

Deterministic diagnostics:
- missing pointer: `WB_POINTER_MISSING`
- stale pointer: `WB_POINTER_STALE`

## Required Loading Order
1. load global bootstrap from `~/.work-bundle/bootstrap.yaml`
2. resolve `work-bundle-root` via `~/.work-bundle/work-bundle-root.yaml`
3. load canonical project metadata from `<project-root>/.work-bundle/project.yaml`
4. verify project Git boundary
5. verify work-bundle Git boundary
6. resolve enabled work-bundle rules for current task
7. load task-specific spec or plan

## Transition Notes
- Do not treat project-local bootstrap markdown as authority.
- Do not encode project identity in global bootstrap authority.
- Do not use split metadata files as runtime authority; use `.work-bundle/project.yaml`.
- For legacy structures, use `/wb-initialize-project doctor` and `/wb-initialize-project migrate`.
- Keep runtime artifacts compact and machine-readable.
