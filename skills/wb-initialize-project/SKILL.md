---
name: wb-initialize-project
description: 'Initialize, validate, doctor, or migrate a project-local work-bundle workspace using canonical bootstrap-resolved project commands.'
---

# wb-initialize-project

Use when a project needs work-bundle initialization, deterministic repair, validation, or migration.

## Commands

Use the unified work-bundle dispatcher:

- Initialize or repair project structure: `python3 scripts/wb.py init-project <project-root> [--name <name>] [--force]`
- Register an existing project root: `python3 scripts/wb.py register-project <project-root> [--name <name>]`
- Inspect project and registry status: `python3 scripts/wb.py show-project --project-root <project-root>`
- Validate project structure: `python3 scripts/wb.py validate-project <project-root>`
- Migrate legacy project structure: `python3 scripts/wb.py migrate-project <project-root>`

`initialize-project` remains a compatibility alias, but new instructions should use `init-project`.

## Behavior

- Resolve runtime roots from `~/.work-bundle/bootstrap.yaml`.
- Create `.work-bundle/knowledge/{context-packs,indexes,notes,open-questions}`.
- Create the full `.work-bundle/orchestration` spec, plan, handoff, and docs substructure during initialization.
- Initialize `.work-bundle/knowledge` as its own Git repository and create its initial deterministic commit when needed.
- Create or preserve `.work-bundle/project.yaml`, `AGENTS.md`, and required `.gitignore` entries.
- Register the project in the bootstrap-resolved global project registry.
- Create a project-level initialization commit when the target project is a Git repository and commit creation is not blocked.

## Boundaries

- Do not create specs, plans, phases, tasks, reviews, or handoffs during initialization.
- Do not delete existing knowledge, orchestration artifacts, registry data, or unknown user files.
- Validation checks file presence, directory structure, schema shape, registry status, and Git status only.
- Migration may add missing deterministic structure and write a migration report, but must preserve existing notes, open questions, orchestration artifacts, Git history, and project identity.
