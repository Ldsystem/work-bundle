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

enforcement:
- must

must:
- know the conception of `work_bundle_config_root`, `work_bundle_root`, and `project_root`
- resolve `work_bundle_config_root` as `~/.work-bundle/`; do not require an environment variable
- read `$work_bundle_config_root/bootstrap.yaml` only when resolving toolkit paths or registries
- resolve `work_bundle_root` from `$work_bundle_config_root/bootstrap.yaml` -> `work_bundle_root`
- resolve project registry from `$work_bundle_config_root/bootstrap.yaml` -> `project_registry`
- resolve skill registry from `$work_bundle_config_root/bootstrap.yaml` -> `skill_registry`
- resolve effective `prefer_subagent` as `.work-bundle/project.yaml` -> `prefer_subagent`, then `$work_bundle_config_root/bootstrap.yaml` -> `prefer_subagent`, then `false`
- treat `prefer_subagent` as permission to prefer sub-agent scheduling only when normal execution safety, write-scope, dependency, and fallback checks pass
- use `work_bundle_root` only for toolkit assets, builtin skills, builtin rules, and references
- use `work_bundle_config_root` only for non-project runtime state produced by tool use

must_not:
- eagerly explore the work-bundle files/skills
- treat `work_bundle_config_root` as project data or toolkit source code
- treat `work_bundle_root` as mutable runtime state
- infer registry paths without reading `bootstrap.yaml` when registry access is required
- let `prefer_subagent` bypass repository preflight, sub-agent capability checks, disjoint write-scope checks, dependency checks, or single-agent fallback
- treat rule-store scope (`toolkit`, `global`, `project`) as separate from rule area directories such as `work-bundle`, `keep-summarizing`, and `orchestration`

## Rule Loading

Rules can be discovered from three rule-store scopes:

- toolkit scope: `$work_bundle_root/rules/index.yaml`
- global user scope: `$work_bundle_config_root/rules/index.yaml`
- project scope: `$project_root/.work-bundle/rules/index.yaml`

Rule loading must be index-first and condition-driven.

After receiving a user request, the agent must decompose it into rule-matching signals, then check discovered rule metadata to find applicable rules.

Rule metadata has separate meanings:

- `load` means when to load the whole rule body into context.
- `applies_when` means when the rule applies to the current workflow.
- `enforcement` means whether an applicable rule is advice or a strict rule that must be followed.

must:
- read enabled rule indexes before loading any rule body
- read `$work_bundle_root/rules/index.yaml`; if it is missing when WorkBundle rule loading is required, stop and report the missing toolkit rule index
- read `$work_bundle_config_root/rules/index.yaml` when it exists; if missing, record that the optional global user rule scope has no rules
- read `$project_root/.work-bundle/rules/index.yaml` when it exists; if missing, record that the optional project rule scope has no rules
- resolve each indexed rule `path` relative to its owning rule-store root
- block rule loading when duplicate rule ids appear across enabled rule-store scopes; report every conflicting scope and path
- block rule loading when `requires` dependencies are missing or cyclic
- load `load: always` rule bodies immediately and unconditionally after their owning index is discovered
- decompose the current user request into task signals, then check all discovered rule metadata against those signals
- identify the task purpose, expected artifact, operation type, target source, file scope, repository scope, lifecycle stage, and tool-relevant conditions when applicable
- treat codebase browsing, code inspection, implementation planning, repair, refactor, migration, review, and editing as distinct operation signals
- treat symbol lookup, dependency tracing, call-chain analysis, module-boundary analysis, and impact-radius analysis as source/condition signals
- check all discovered rule metadata against the decomposed purpose, source, conditions, operation type, artifact type, and file scope
- mark all rules whose `applies_when` matches any material decomposed signal as applicable to the current workflow
- load `load: conditional` rule bodies when their `applies_when` conditions match the decomposed task signals
- load `load: manual` rules only when explicitly requested by the user, selected skill, selected role, or another loaded rule
- load rule dependencies declared in `requires` after the parent rule has been selected
- apply every applicable rule according to `enforcement`: `must` means strict compliance; `should` means advice that must be reported when materially deviated from
- load only Markdown rule files referenced by discovered index metadata or dependency resolution
- when diagnostic mode is requested, report discovered scopes, missing optional scopes, applicable rules, loaded rules, always-loaded rules, skipped rules, dependency-loaded rules, conflicts, and the reason for each decision

must_not:
- do not load all rule bodies eagerly
- do not gate `load: always` body loading on `applies_when`, current task relevance, operation type, artifact type, file scope, repository scope, or session scope
- do not use vague similarity alone to select rules; selection must be justified by `applies_when`, enforcement, operation type, artifact type, file scope, source, conditions, or explicit dependency
- do not silently override toolkit rules with global user or project rules that use the same id
- do not edit, create, delete, migrate, or index `$work_bundle_root/rules/**` unless `$project_root` is equal to `$work_bundle_root`

on_failure:
- if `rules/index.yaml` is missing when rule loading is required, stop and report that the rule index is unavailable
- if a selected rule path is missing, stop the affected operation and report the missing rule path
- if rule front matter conflicts with index metadata, prefer the rule file as source of truth and report the index inconsistency
- if duplicate rule ids, missing dependencies, or dependency cycles are found, stop rule loading and report the conflicting rule-store scopes and paths
