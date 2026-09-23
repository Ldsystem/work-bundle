---
name: wb-register-skill
description: 'Inspect an external skill, propose role/stage/output mappings, and write external-registry updates only after confirmation. Built-in WorkBundle skills are excluded.'
---

# wb-register-skill

Never blindly register skills. This workflow is only for external skills. Built-in skills under `$work_bundle_root/skills/` are toolkit-owned and must never be copied into the runtime registry. Inspect external instructions, propose a compact `type: external` registry entry, validate role and stage identifiers from the registry contract, then merge only with confirmation. These identifiers do not require toolkit-source `roles/*.yaml` profiles.

## Scripts

Use the unified work-bundle dispatcher:

The examples use the macOS/Linux `python3` launcher. On Windows, use `py -3.13` or a resolved `python` executable instead.

- Inspect candidate skill: `python3 scripts/wb.py inspect-skill <skill-file>`
- Validate registry entry: `python3 scripts/wb.py validate-registry-entry <entry-file>`
- Merge confirmed external entry: `python3 scripts/wb.py register-skill --registry ~/.work-bundle/registry/skill-registry.yaml --entry <entry-file> --confirmed`

Resolve the actual registry path from `~/.work-bundle/bootstrap.yaml` field `skill_registry`; the path above is the canonical default, not an authority override. Never call the merge command before the user has confirmed the proposed role/stage/output mapping. Refuse registration when the candidate is a built-in WorkBundle skill or the entry is not `type: external`.
