---
name: wb-select-role-context
description: 'Resolve lifecycle stage, perspective, stable role profiles, project domain positioning, and skill hints without browsing durable knowledge. Work-bundle scoped as wb-select-role-context.'
---

# wb-select-role-context

Returns compact role_context JSON/YAML. It may read bootstrap files, domain profile, role mappings, global registry, optional project override, and source artifacts. It must not browse `.work-bundle/knowledge/` directly.


## Core prompt

You should find a proper role according to the current task, current lifecycle stage, and perspective. Work as this role and complete the task.

Resolve the role from stable role profiles and project/domain context rather than inventing a new one. Return only the compact role_context JSON/YAML needed by the caller.

If no stable role can be matched from current stage/perspective, return one draft role instead of multiple candidates:

- include `resolution: fallback-draft-role`
- set `primary_role` to the draft role and continue working as this role directly
- keep `supporting_roles` empty by default in fallback mode
- include `draft_role` with role profile `stance`, `capabilities` (`skilled_at`), `duties` (`quality_focus`), and `must_resolve_from_context`
- keep output machine-usable while making fallback rationale explicit for later user confirmation

## Scripts

Use the unified work-bundle dispatcher:

- Resolve role context: `python3 scripts/wb.py select-role-context --project-root <project-root> --directive <directive> [--source-artifact <path>] [--stage <stage>] [--perspective <perspective>]`
- Validate saved role context: `python3 scripts/wb.py validate-role-context <role-context-file>`
