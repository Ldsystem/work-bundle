---
name: wb-manage-repository-model
description: 'Manage v4 project/work-bundle repository boundaries, AGENTS.md, .gitignore, repository binding, and rules root idempotently. Canonical work-bundle skill name: wb-manage-repository-model.'
---

# wb-manage-repository-model

Use for repository boundary inspection, repair, and validation.

Rules:
- Keep project Git and `.work-bundle` Git separate.
- Ensure project `.gitignore` ignores `.work-bundle/` and `AGENTS.md`.
- Ensure `.work-bundle/.gitignore` owns work-bundle exclusions.
- Write compact bootstrap artifacts only under `references/bootstrap/`.
- Do not commit automatically.

## Scripts

Use the unified work-bundle dispatcher:

- Inspect repository model: `python3 scripts/wb.py inspect-repository-model <project-root>`
- Apply repository model repair: `python3 scripts/wb.py repository-model <project-root>`
- Validate repository model: `python3 scripts/wb.py validate-repository-model <project-root>`
