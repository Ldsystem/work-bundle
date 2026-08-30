---
name: wb-create-rule
description: 'Create, update, migrate, and validate Markdown work-bundle runtime rules under rules/ using the index-first rule contract. Canonical work-bundle skill name: wb-create-rule.'
---

# wb-create-rule

Use when creating, updating, migrating, or validating work-bundle rule files.

This skill is the primary agent authority for rule creation. It is self-contained; do not load non-git paths as authority.

## Authority Boundary

Authority for rule work is limited to:

- `skills/wb-create-rule/SKILL.md` — this skill (primary agent contract).
- `$work_bundle_root/rules/` — toolkit runtime rules and `index.yaml` when rule-store scope is `toolkit`.
- `$work_bundle_config_root/rules/` — global user runtime rules and `index.yaml` when rule-store scope is `global`.
- `$workspace_root/.work-bundle/rules/` — workspace project-scope runtime rules and `index.yaml` when rule-store scope is `project`.
- `$project_root/.work-bundle/rules/` — compatibility alias only when `project_root == workspace_root`; never use a multi-repository member root as project rule authority.
- `references/wb-create-rule-validation.yaml` — mechanical validation catalogs
- `scripts/wb.py` — dispatcher for `create-rules` and `validate-rules`

**Must not** cite paths outside the selected rule-store root, this skill, the validation catalog, or the dispatcher as rule authority. Offline or untracked material outside those selected authority paths may inform human spec authoring only; agents must not load or reference it when creating, migrating, or validating rules.

## Rule Store Scopes

Rule-store scope chooses which rules root is created, synced, or validated:

| Rule-store scope | Rules root | Use |
|---|---|---|
| `toolkit` | `$work_bundle_root/rules/` | Built-in WorkBundle rules. |
| `global` | `$work_bundle_config_root/rules/` | User-customized global rules. |
| `project` | `$workspace_root/.work-bundle/rules/` | Workspace project-scope rules shared by its members. |
| `explicit` | user-supplied `<rules-root>` | Backward-compatible direct root mode. |

Rule-store scope is not the same as a rule area directory. Area directories inside any rules root remain `work-bundle/`, `keep-summarizing/`, and `orchestration/`.

**Toolkit write boundary:** agents must not create, edit, delete, migrate, or index `$work_bundle_root/rules/**` unless `$workspace_root == $work_bundle_root`. If the active workspace root is different from the toolkit root, stop with a boundary blocker instead of mutating toolkit rules.

## Rule Layout

```text
<rules-root>/
  index.yaml
  <cross-cutting-rule>.md          # cross-cutting rules at repo root level
  work-bundle/
    wb-*.md
  keep-summarizing/
    ks-*.md
  orchestration/
    orch-*.md
```

| Rule kind | Location | When to use |
|---|---|---|
| **Scoped** | `<rules-root>/<scope>/<rule-id>.md` | Rule owned by a skill area; id uses an area prefix |
| **Cross-cutting** | `<rules-root>/<rule-id>.md` directly under the rules root | Rule applies across areas without a single owner prefix |

There is **no** `global/` area directory inside a rules root. Global rules use rule-store scope `global` and still place cross-cutting rules directly at `$work_bundle_config_root/rules/`.

### Scope and id prefix map

| Id prefix | Target scope directory |
|---|---|
| `wb-` | `rules/work-bundle/` |
| `ks-` | `rules/keep-summarizing/` |
| `orch-` | `rules/orchestration/` |
| no area prefix / cross-cutting | `<rules-root>/` |

Allowed scope directory names are enumerated in `references/wb-create-rule-validation.yaml` under `allowed_scopes`. Mechanical path placement checks use `id_prefix_scope_map` and `path_rules` from that manifest.

## Rule Contract

Rules are Markdown files with YAML front matter and an enforceable body.

### Required front matter

```yaml
---
id: <rule-id>
applies_when:
  - <concrete condition>
enforcement: must|should
load: always|conditional|manual
requires: []
---
```

### Required body sections

```markdown
# <Rule Title>

## Purpose

## Must

## Must Not

## Validation

## On Violation
```

### Index entry (canonical)

Every registered rule appears in the owning rules root's `index.yaml`:

```yaml
rules:
  - id: <rule-id>
    path: <scope-or-root>/<file>.md
    applies_when:
      - <concrete condition>
    enforcement: must|should
    load: conditional
    requires: []
```

Index metadata must mirror rule front matter. Path values are stable from the rules root (for example `work-bundle/wb-create-rule.md`).

## Reference Manifest

Mechanical catalogs live in `references/wb-create-rule-validation.yaml`:

- `required_front_matter`, `required_body_sections`
- `prohibited_rule_fields`
- `allowed_scopes`, `allowed_scope_patterns`
- `id_prefix_scope_map`
- `path_rules` (`scoped`, `cross_cutting`, `forbidden`)

Scripts load this manifest for mechanical checks. Agents use it when verifying placement and field compliance; semantic judgment stays agent-owned (see below).

## Commands and Index Workflow

Use the unified work-bundle dispatcher. Prefer scoped commands:

| Command | Behavior |
|---|---|
| `python3 scripts/wb.py create-rules --scope toolkit` | Sync toolkit rules; allowed only when `$project_root == $work_bundle_root`. |
| `python3 scripts/wb.py create-rules --scope global` | Sync global user rules under `$work_bundle_config_root/rules/`. |
| `python3 scripts/wb.py create-rules --scope project --workspace-root <workspace-root>` | Sync project-scope rules under `<workspace-root>/.work-bundle/rules/`. |
| `python3 scripts/wb.py validate-rules --scope toolkit` | Validate toolkit rules. |
| `python3 scripts/wb.py validate-rules --scope global` | Validate global user rules. |
| `python3 scripts/wb.py validate-rules --scope project --workspace-root <workspace-root>` | Validate workspace project-scope rules. |
| `python3 scripts/wb.py create-rules <rules-root>` | Backward-compatible explicit-root mode. |
| `python3 scripts/wb.py validate-rules <rules-root>` | Backward-compatible explicit-root mode. |

The selected rules root must be the canonical root for that rule-store scope. Do not pass area subdirectories such as `rules/work-bundle/`; those create incorrect nested indexes and are rejected by the scripts.

Typical workflow:

1. Resolve rule-store scope (`toolkit`, `global`, `project`, or explicit root) and confirm toolkit writes are allowed when scope is `toolkit`.
2. Create or update the rule Markdown file at the correct scoped or root path.
3. Ensure front matter and body sections match this contract.
4. Run agent semantic checks on `applies_when` (see below).
5. Run `python3 scripts/wb.py create-rules --scope <scope>` or explicit-root compatibility mode to refresh the index for touched paths.
6. Run `python3 scripts/wb.py validate-rules --scope <scope>` or explicit-root compatibility mode for mechanical confirmation.

Prefer validating only paths you changed; full-tree validation may fail until legacy corpus migration completes.

## Legacy YAML → Markdown Migration

For agent-led manual migration of individual legacy YAML rule files:

| Legacy field | Markdown target | Notes |
|---|---|---|
| `id` | front matter `id` | unchanged |
| `applies_when` or `enable_when` | front matter `applies_when` | list of concrete conditions |
| `enforcement` or `severity` | front matter `enforcement` | `warning` / `should` → `should`; otherwise `must` |
| `load` | front matter `load` | default `conditional` |
| `requires` | front matter `requires` | list or `[]` |
| `required_behavior` | body `## Must` | bullet list |
| `prohibited_behavior` | body `## Must Not` | bullet list |
| `validation` | body `## Validation` | bullet list |
| `scope`, `type`, `blocks`, `severity` (as legacy front matter), `status`, `source_authority` | **drop** | do not carry into Markdown front matter |

After migration:

- Place the file using the scope/id prefix map above.
- Remove the legacy `.yaml` source once the Markdown rule is verified.
- Run `create-rules` then `validate-rules` on the affected rule-store scope or explicit rules root.

`create-rules` can mechanically convert legacy YAML when an `id` field is present; agents still own semantic review of migrated `applies_when` and body prose.

## Agent Semantic Validation (`applies_when`)

**Boundary:** Scripts check mechanical presence and format only. Agents own semantic evaluation of `applies_when`.

| Owner | Checks |
|---|---|
| **Script (mechanical)** | `applies_when` key exists; value is a non-empty list; front matter keys match manifest; path placement; prohibited fields absent; line limit; index sync |
| **Agent (semantic)** | Each condition is concrete and actionable; activation logic is clear; conditions are enforceable without reading external authority |

Before registering a rule, the agent **must** reject vague or non-actionable `applies_when` entries. Prohibited vague patterns include:

- `when relevant`, `if relevant`, `as relevant`
- `if needed`, `when needed`, `as needed`
- `as appropriate`, `when appropriate`
- `if applicable`, `when applicable`
- `when working on related tasks`, `for general use`

**Mechanical example (script passes):**

```yaml
applies_when:
  - when relevant
```

**Semantic example (agent must reject):** same entry — condition is not concrete.

**Good example (agent accepts):**

```yaml
applies_when:
  - user requests creation of a new work-bundle script
  - agent maintains scripts under scripts/
```

Scripts will **not** judge `applies_when` meaning or reject vague tokens. That responsibility belongs to the agent via this skill.

## Trigger Clarity Principle

Rule trigger prose must name the user-visible or workflow-visible signal that causes rule consideration before describing rule lookup, selection, or application. Do not make activation depend on the agent first realizing that it is in a "rule selection" step; an agent that has not recognized a rule need may never enter that step.

Prefer trigger constructions that start from observable work:

- "When a user request is received, decompose it into task signals, then check discovered rules."
- "When a user asks to create or edit a rule, load `wb-create-rule`."
- "When decomposed task signals include source inspection, check CodeGraph applicability."

Reject unclear trigger constructions:

- `before rule selection`
- `when selecting rules` as the only trigger
- `when needed`, `when relevant`, `when appropriate`
- any instruction where the agent must already know a rule is relevant before the instruction explains how to detect relevance

## `source_authority` and `enforcement: should`

- Do not use `source_authority` in front matter. Extract enforceable requirements into `## Must`, `## Must Not`, and `## Validation` so the rule body is self-contained.
- `enforcement: must` — violation blocks the operation; stop and correct before continuing.
- `enforcement: should` — violation is a deviation; report the deviation explicitly and proceed only when the user or task accepts the trade-off.

## Must

- Create one rule per enforceable contract.
- Keep each rule concise and under 500 lines.
- Put activation logic in `applies_when` using concrete conditions.
- Use `enforcement` to define mandatory or expected force.
- Register every rule in `rules/index.yaml` with synchronized metadata.
- Place scoped rules under the correct `rules/<scope>/` directory per the prefix map.
- Place cross-cutting rules at `rules/<rule-id>.md` (root), never under `rules/global/`.
- Prefer `load: conditional` unless startup loading is explicitly required.
- Run `validate-rules --scope <toolkit|global|project>` or explicit-root compatibility mode after rule work; never on area subdirectories.
- Inspect `applies_when` semantically before completing registration.
- Apply the Trigger Clarity Principle to `applies_when` and rule prose: name the observable trigger before rule lookup, selection, or application language.

## Must Not

- Do not use legacy front matter fields: `scope`, `type`, `blocks`, `severity`, `status`, or `source_authority`.
- Do not register documentation-only notes as rules.
- Do not create broad rules that require agents to read unrelated source documents.
- Do not create `.mdc` rule files.
- Do not cite paths outside the selected rule-store root, this skill, the validation catalog, or the dispatcher as rule authority.
- Do not create or document a `global/` area directory inside any rules root.
- Do not run `create-rules` or `validate-rules` against scope subdirectories such as `rules/work-bundle/`.
- Do not mutate toolkit rules when `$workspace_root != $work_bundle_root`.
- Do not rely on scripts to judge `applies_when` semantics.
- Do not use `before rule selection` or `when selecting rules` as the only trigger for rule consideration.

## Validation

**Agent (before completion):**

- Confirm correct path (scoped vs cross-cutting) per prefix map.
- Confirm front matter and body sections match this contract.
- Confirm `applies_when` conditions are concrete (no vague tokens).
- Confirm trigger prose names an observable user or workflow signal before rule lookup, selection, or application language.
- Confirm index entry mirrors front matter.
- Confirm no prohibited legacy fields are present.

**Mechanical (script):**

```bash
python3 scripts/wb.py validate-rules --scope <toolkit|global|project>
```

## Runtime Rules

- `wb-create-rule`: `rules/work-bundle/wb-create-rule.md`
- `wb-project-context-preflight`: `rules/work-bundle/wb-project-context-preflight.md`
- `wb-script-instruction`: `rules/work-bundle/wb-script-instruction.md` when rule work changes script/lifecycle instructions.
- `rule-work-bundle-security-exclusion`: `rules/security-exclusion.md` when a rule touches credential-bearing surfaces.

## On Violation

Stop rule creation or migration, report the violated field or section, and make the minimal correction before registering the rule. For `enforcement: should` rules, report deviations explicitly instead of silently continuing.
