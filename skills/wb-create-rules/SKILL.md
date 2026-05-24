---
name: wb-create-rules
description: 'Create or validate compact YAML v4 work-bundle runtime rules under references/rules/. Canonical work-bundle skill name: wb-create-rules.'
---

# wb-create-rules

Creates compact YAML rules only. Never generates `.mdc`; deprecated `.mdc` files may appear only under `deprecated_sources`.

## Scripts

Use the unified work-bundle dispatcher:

- Create or refresh rules: `python3 scripts/wb.py create-rules references/rules`
- Validate rules: `python3 scripts/wb.py validate-rules references/rules`
