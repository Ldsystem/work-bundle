---
name: wb-register-skill
description: 'Inspect a skill, propose role/stage/output mappings, and write registry updates only after confirmation. Work-bundle scoped as wb-register-skill.'
---

# wb-register-skill

Never blindly register skills. Inspect instructions, propose compact registry entry, validate stable roles/stages, then merge only with confirmation.

## Scripts

Use the unified work-bundle dispatcher:

- Inspect candidate skill: `python3 scripts/wb.py inspect-skill <skill-file>`
- Validate registry entry: `python3 scripts/wb.py validate-registry-entry <entry-file>`
- Merge confirmed entry: `python3 scripts/wb.py register-skill --registry ~/.work-bundle/skills/skill-registry.yaml --entry <entry-file> --confirmed`

Never call the merge command before the user has confirmed the proposed role/stage/output mapping.
