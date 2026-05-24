# Agent Bootstrap

## Project Identity
project: keep-summarizing

## Repository Layout
work_bundle: .work-bundle
source_code_root: .

## Git Boundary
Project Git and work-bundle Git are separate. Do not mix commit scopes by default.

## Project Gitignore
.gitignore must ignore .work-bundle/ and AGENTS.md.

## Work Bundle Git Repository
.work-bundle/.git

## Knowledge Source of Truth
.work-bundle/knowledge/

## Orchestration Artifact Root
.work-bundle/orchestration/

## Work Bundle Rules Root
references/rules/

## Project Agents Entry
AGENTS.md

## Required Loading Order
1. repository-binding.md
2. verify project Git boundary
3. verify work-bundle Git boundary
4. agent-bootstrap.md
5. load work-bundle rules contract and rule index
6. resolve enabled work-bundle rules for current task
7. project.yaml
8. project-domain-profile.yaml
9. identify current lifecycle stage
10. load relevant stage-first notes only through allowed gateway/directive rules
11. classify retrieved notes by status and retrieval role
12. load relevant open-question records when allowed
13. select primary role profile by lifecycle stage
14. select supporting role profiles by leaf perspective
15. locate customized skill root
16. load global skill registry
17. load optional project skill registry override if present
18. load task-specific spec or plan

## Available Role Profiles
references/roles/

## Available Skill Registry
~/.work-bundle/skills/skill-registry.yaml

## Customized Skill Root
/Users/shenglong/Documents/Repository/work-bundle/skills

## Project Skill Override
optional: .work-bundle/orchestration/skill-registry.override.yaml

## Project Registry
The optional global project registry lives at `~/.work-bundle/registry/projects.yaml` unless `KS_PROJECT_REGISTRY` or `--registry-file` overrides it.

Use it only as local runtime state for project discovery. Do not copy it into skill resources, durable project knowledge, orchestration artifacts, or reusable templates.

Resolution priority:

1. explicit `--knowledge-root`
2. explicit `--project-root`
3. walk upward from `--cwd` or current directory to find `.work-bundle/knowledge`
4. global project registry by slug, alias, work-bundle root, or source repository path
5. explicit external legacy root for migration/read-only intake

## Enabled Work Bundle Rules
Resolve from references/rules/index.yaml before directive-specific behavior.

## Output Rules
Keep runtime artifacts compact and machine-readable. Prefer compact YAML for runtime rules, role profiles, domain profile, and role context.

## Handoff Rules
Use .work-bundle/orchestration/handoff/. Executor handoffs carry role_context_used when available.

## Forbidden Behavior
Do not write durable knowledge from orchestration directives. Do not generate .mdc rules. Do not treat deprecated .mdc files as current authority.
