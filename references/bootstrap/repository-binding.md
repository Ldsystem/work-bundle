# Repository Binding (Deprecated Authority)

This file is retained only as a compatibility reference.
Canonical project metadata authority is `<project-root>/.work-bundle/project.yaml`.

## Migration owner
- `/wb-initialize-project`

## Deterministic migration guidance
- Doctor legacy structure: `/wb-initialize-project doctor`
- Migrate to canonical metadata: `/wb-initialize-project migrate`

## Last observed repository state (non-authoritative)
```yaml
project_root: /Users/shenglong/Documents/Repository/work-bundle
project_git_exists: true
project_gitignore: /Users/shenglong/Documents/Repository/work-bundle/.gitignore
project_ignores_work_bundle: true
project_ignores_agent_entry: true
work_bundle_root: /Users/shenglong/Documents/Repository/work-bundle/.work-bundle
work_bundle_git_repo: true
work_bundle_gitignore: /Users/shenglong/Documents/Repository/work-bundle/.work-bundle/.gitignore
agent_entry_path: /Users/shenglong/Documents/Repository/work-bundle/AGENTS.md
project_skill_override: not configured
global_skill_registry: ~/.work-bundle/skills/skill-registry.yaml
customized_skill_root: /Users/shenglong/Documents/Repository/work-bundle/skills
```
