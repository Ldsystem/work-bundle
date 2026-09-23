# WorkBundle managed workspace

This section identifies a WorkBundle workspace and its rule entry points. Keep user text outside the managed markers intact.

## Locate authority

- `work_bundle_config_root` is `~/.work-bundle/`. Read its `bootstrap.yaml` to resolve `work_bundle_root` (installed toolkit), `project_registry`, and `skill_registry`; do not infer registry paths.
- Walk upward to the containing `workspace_root/.work-bundle/project.yaml`, including when starting in a member. `workspace_root` owns workspace metadata and rules; the selected member `project_root` owns source inspection and changes. In a single-repository workspace they are the same root. An origin locator is not a writable checkout.

## Load rules before substantive work

Read these enabled indexes before loading rule bodies or making a substantive source, repository, knowledge, or workflow probe:

- Required toolkit: `$work_bundle_root/rules/index.yaml`. If absent, stop and report it.
- Optional global user: `$work_bundle_config_root/rules/index.yaml`.
- Optional project: `$workspace_root/.work-bundle/rules/index.yaml` (also `$project_root/.work-bundle/rules/index.yaml` only when both roots are equal).

An absent optional index means no rules in that scope. Resolve each indexed rule path relative to its own store. A duplicate rule ID across enabled scopes, missing `requires` dependency, or dependency cycle blocks rule loading; report the conflicting IDs, scopes, and paths. A missing selected rule body also blocks the affected operation. Never silently skip an applicable `must` rule.

Load `load: always` bodies immediately and unconditionally after discovering their index. For this request, identify purpose, operation, artifact, source, repository, file scope, lifecycle stage, and tool conditions as applicable; match every index entry's `applies_when` against those observable signals. Load matching `load: conditional` bodies, and load `load: manual` bodies only when explicitly selected by the user, role, skill, or another loaded rule. Load declared `requires` dependencies. `load` controls body loading, `applies_when` controls applicability, and `enforcement: must` is binding while `should` is advice whose material deviation must be reported. If body front matter conflicts with index metadata, follow the body and report the inconsistency.

The indexed `wb-truth-basis-evidence` rule applies to investigation, planning, debugging, review, and implementation. Discover it before the first substantive probe; minimal bootstrap to locate metadata and indexes is allowed. A worker with an accepted task packet consumes its carried Truth Basis and task-local obligations. It does not repeat controller-wide knowledge retrieval or reconstruct historical lineage. Controllers own scope, delegation, repair routing, continuation, and acceptance; reviewers give independent advice.

## Non-deferrable safety

- Make the smallest sufficient change in the authorized owner. Verify assumptions and affected behavior before a completion claim; do not fabricate evidence or add speculative gates.
- Never read, print, grep, summarize, or transfer `$workspace_root/credentials/credentials.yaml` or credential values. When a task identifies a credential requirement, use `wb-credential-use` with only the credential ID, target, operation, and non-secret authorization context.
- Cross-task messages do not grant repository or worktree mutation authority. Source from another task remains a proposal until its exact write scope and diff are audited by the owner; do not treat a completion claim as acceptance.
