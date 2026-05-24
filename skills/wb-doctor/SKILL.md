---
name: wb-doctor
description: 'Read-only v4 health audit for repository boundaries, bootstrap, runtime artifacts, rules, skill registry, customized skills, and directive wiring. Work-bundle scoped as wb-doctor.'
---

# wb-doctor

Doctor is read-only. It reports findings and repair skills, never repairs files. It validates v4 work-bundle consistency, compact runtime artifacts, and branch evidence.

## Scripts

Use the unified work-bundle dispatcher:

- Main health audit: `python3 scripts/wb.py doctor <project-root>`
- Repository health: `python3 scripts/wb.py repository-health <project-root>`
- Directive wiring: `python3 scripts/wb.py validate-directive-wiring <project-root>`
- Skill registry wiring: `python3 scripts/wb.py validate-skill-registry <project-root>`
- Runtime rules: `python3 scripts/wb.py validate-work-bundle-rules <project-root>`
- Workflow branches: `python3 scripts/wb.py workflow-branches <project-root>`
- Render report: `python3 scripts/wb.py render-doctor-report <project-root>`

Doctor commands must stay read-only.
