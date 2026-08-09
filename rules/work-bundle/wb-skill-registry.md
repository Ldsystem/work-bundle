---
id: wb-skill-registry
applies_when:
  - task.registers_external_skill
  - task.resolves_available_skills
  - task.resolves_role_skills
  - task.resolves_stage_skills
enforcement: must
load: conditional
requires: []
---

# Skill Registry

## Purpose

Ensure external-skill registration and resolution use the bootstrap-resolved external skill registry while built-in WorkBundle skills remain toolkit-owned.

## Must

- Resolve the skill registry path from `$work_bundle_config_root/bootstrap.yaml` field `skill_registry`.
- Use the skill registry only to register and resolve external skills for a role, stage, or work type.
- Discover built-in WorkBundle skills through toolkit-owned skill surfaces; do not copy or register them in the runtime registry.
- Keep skill registry state under `work_bundle_config_root`.

## Must Not

- Do not discover available runtime skills by eagerly scanning all skill directories.
- Do not add a skill under `$work_bundle_root/skills/` to the external runtime registry.
- Do not treat an unregistered external skill as available through the external runtime registry.
- Do not store skill registry state under `work_bundle_root` or `project_root`.

## Validation

- Inspect skill registration and resolution commands for bootstrap-resolved registry paths.
- Verify external-skill resolution reads registry state rather than scanning arbitrary external skill locations.
- Verify built-in WorkBundle skills are absent from the external registry and remain available through toolkit skill discovery.
- Verify no project-local skill registry copy is used as global runtime authority.

## On Violation

Stop external-skill resolution or registration and report the missing registry path, non-external entry, missing skill metadata, or misplaced registry state. Reject any attempt to register a built-in WorkBundle skill.
