---
id: wb-skill-registry
applies_when:
  - task.registers_skill
  - task.resolves_available_skills
  - task.resolves_role_skills
  - task.resolves_stage_skills
enforcement: must
load: conditional
requires: []
---

# Skill Registry

## Purpose

Ensure skill registration and skill resolution use the bootstrap-resolved skill registry instead of eager scans or project-local copies.

## Must

- Resolve the skill registry path from `$work_bundle_config_root/bootstrap.yaml` field `skill_registry`.
- Use the skill registry to register work-bundle skills and resolve available skills for a role, stage, or work type.
- Keep skill registry state under `work_bundle_config_root`.

## Must Not

- Do not discover available runtime skills by eagerly scanning all skill directories.
- Do not treat unregistered skill files as available runtime skills.
- Do not store skill registry state under `work_bundle_root` or `project_root`.

## Validation

- Inspect skill registration and resolution commands for bootstrap-resolved registry paths.
- Verify runtime skill resolution reads registry state rather than scanning all skills.
- Verify no project-local skill registry copy is used as global runtime authority.

## On Violation

Stop skill resolution or registration and report the missing registry path, missing skill metadata, or misplaced registry state.
