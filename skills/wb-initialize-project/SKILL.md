---
name: wb-initialize-project
description: 'Initialize or repair v4 project-local work-bundle structure, bootstrap files, runtime roots, and repository boundary. Canonical work-bundle skill name: wb-initialize-project.'
---

# wb-initialize-project

Use to prepare a project for v4 work-bundle operation. Runtime outputs should be compact and machine-readable. Do not copy the global skill registry into projects.

## Scripts

Use the unified work-bundle dispatcher:

- Inspect only: `python3 scripts/wb.py inspect-project-initialization <project-root>`
- Initialize or repair: `python3 scripts/wb.py initialize-project <project-root>`
- Validate: `python3 scripts/wb.py validate-project <project-root> --dry-run`

Initialization must create canonical bootstrap files under `references/bootstrap/`.
