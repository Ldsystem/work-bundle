# Work Bundle
purpose:
- Seeing this rule means that you are working with the `work-bundle` toolkit, it provides skills and rules to finish a bunch of works, including:
  - Work bundle skills: `/wb-*`, provide skills to manage a project as a `work-bundle` adapted workspace.
  - Keep summarizing skills: `/ks-*`, provide skills to compile knowledge into atomic notes, browsing knowledge base for helpful notes against current purpose, etc.
  - Orchestration skills: `orch-*`, provide skills for feature-implementation orchestration, including evidence gathering, specification/plan creation, execution instruction, verifying, etc.
  - General conception:
  - `work_bundle_root`: path to the `work-bundle` toolkit installation directory.
  - `work_bundle_config_root`: state files root of the toolkit.
  - `project_root`: path to a concrete project

applies_when:
- always

severity:
- must

must:
- know the conception of `work_bundle_config_root`, `work_bundle_root`, and `project_root`
- resolve `work_bundle_config_root` as `~/.work-bundle`; do not require an environment variable
- read `$work_bundle_config_root/bootstrap.yaml` only when resolving toolkit paths or registries
- resolve `work_bundle_root` from `$work_bundle_config_root/bootstrap.yaml` -> `work_bundle_root`
- resolve project registry from `$work_bundle_config_root/bootstrap.yaml` -> `project_registry`
- resolve skill registry from `$work_bundle_config_root/bootstrap.yaml` -> `skill_registry`
- use `work_bundle_root` only for toolkit assets, builtin skills, builtin rules, and references
- use `work_bundle_config_root` only for non-project runtime state produced by tool use

must_not:
- eagerly explore the work-bundle files/skills
- treat `work_bundle_config_root` as project data or toolkit source code
- treat `work_bundle_root` as mutable runtime state
- infer registry paths without reading `bootstrap.yaml` when registry access is required
- load full rule bodies before rule metadata has matched the current task

## Rule Loading

Rules are stored under `$work_bundle_root/rules/`.

Rule loading must be index-first and condition-driven.

must:
- read `$work_bundle_root/rules/index.yaml` before loading any rule body
- select rules by matching index metadata against the current task purpose, artifact type, operation type, and file scope
- load `load: always` rules only when their scope is relevant to the current work-bundle session
- load `load: conditional` rules only when their `applies_when` conditions match the current task
- load `load: manual` rules only when explicitly requested by the user, selected skill, selected role, or another loaded rule
- load rule dependencies declared in `requires` after the parent rule has been selected
- load only the selected Markdown rule files referenced by `path`
- apply loaded rules according to `severity` and `blocks`
- when diagnostic mode is requested, report selected rules, skipped rules, dependency-loaded rules, and the reason for each decision

must_not:
- do not load all rule bodies by default
- do not load a rule body before its index metadata has matched the current task
- do not follow `source_authority`; current rules must be self-contained
- do not treat deprecated `.mdc` files as active rules
- do not use vague similarity alone to select rules; selection must be justified by `applies_when`, `scope`, `type`, `blocks`, or explicit dependency
- do not load unrelated skill, stage, perspective, or project rules only because they exist in the index

on_failure:
- if `rules/index.yaml` is missing when rule loading is required, stop and report that the rule index is unavailable
- if a selected rule path is missing, stop the affected operation and report the missing rule path
- if rule front matter conflicts with index metadata, prefer the rule file as source of truth and report the index inconsistency
