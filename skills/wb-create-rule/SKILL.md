---
name: wb-create-rule
description: 'Create, update, migrate, and validate Markdown work-bundle runtime rules under rules/ using the index-first rule contract. Canonical work-bundle skill name: wb-create-rule.'
---

# wb-create-rule

Use when creating, updating, migrating, or validating work-bundle rule files.

This skill is the primary agent authority for rule creation. It is self-contained; do not load non-git paths as authority.

## Authority Boundary

Git-tracked authority for rule work is limited to:

- `skills/wb-create-rule/SKILL.md` — this skill (primary agent contract)
- `rules/` — runtime rules and `rules/index.yaml`
- `references/wb-create-rule-validation.yaml` — mechanical validation catalogs
- `scripts/wb.py` — dispatcher for `create-rules` and `validate-rules`

**Must not** cite paths outside the git repository as authority. Offline or untracked material (for example paths under a local `design/` tree) may inform human spec authoring only; agents must not load or reference them when creating, migrating, or validating rules.

## Rule Layout

```text
rules/
  index.yaml
  <cross-cutting-rule>.md          # cross-cutting rules at repo root level
  work-bundle/
    wb-*.md
  keep-summarizing/
    ks-*.md
  orchestration/
    orch-*.md
  integrity-check/
    rule-integrity-check-*.md
```

| Rule kind | Location | When to use |
|---|---|---|
| **Scoped** | `rules/<scope>/<rule-id>.md` | Rule owned by a skill area; id uses an area prefix |
| **Cross-cutting** | `rules/<rule-id>.md` directly under `rules/` | Rule applies across areas without a single owner prefix |

There is **no** `rules/global/` directory. Cross-cutting rules belong at `rules/` root, not under a `global/` subdirectory.

### Scope and id prefix map

| Id prefix | Target scope directory |
|---|---|
| `wb-` | `rules/work-bundle/` |
| `ks-` | `rules/keep-summarizing/` |
| `orch-` | `rules/orchestration/` |
| `rule-integrity-check-` | `rules/integrity-check/` |
| no area prefix / cross-cutting | `rules/` (root) |

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

Every registered rule appears in `rules/index.yaml`:

```yaml
rules:
  - id: <rule-id>
    path: rules/<scope-or-root>/<file>.md
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

Use the unified work-bundle dispatcher:

| Command | Behavior |
|---|---|
| `python3 scripts/wb.py create-rules <rules-root>` | Migrate legacy YAML rules to Markdown where applicable; sync `index.yaml` for discovered rules |
| `python3 scripts/wb.py validate-rules <rules-root>` | Mechanical validation; non-zero exit on failures |

Typical workflow:

1. Create or update the rule Markdown file at the correct scoped or root path.
2. Ensure front matter and body sections match this contract.
3. Run agent semantic checks on `applies_when` (see below).
4. Run `python3 scripts/wb.py create-rules <rules-root>` to refresh the index for touched paths.
5. Run `python3 scripts/wb.py validate-rules <rules-root>` on touched paths for mechanical confirmation.

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
- Run `create-rules` then `validate-rules` on the affected rules root.

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
- Run `validate-rules` on touched paths after rule work.
- Inspect `applies_when` semantically before completing registration.

## Must Not

- Do not use legacy front matter fields: `scope`, `type`, `blocks`, `severity`, `status`, or `source_authority`.
- Do not register documentation-only notes as rules.
- Do not create broad rules that require agents to read unrelated source documents.
- Do not create `.mdc` rule files.
- Do not cite non-git paths as authority.
- Do not create or document a `rules/global/` directory.
- Do not rely on scripts to judge `applies_when` semantics.

## Validation

**Agent (before completion):**

- Confirm correct path (scoped vs cross-cutting) per prefix map.
- Confirm front matter and body sections match this contract.
- Confirm `applies_when` conditions are concrete (no vague tokens).
- Confirm index entry mirrors front matter.
- Confirm no prohibited legacy fields are present.

**Mechanical (script):**

```bash
python3 scripts/wb.py validate-rules <rules-root>
```

## On Violation

Stop rule creation or migration, report the violated field or section, and make the minimal correction before registering the rule. For `enforcement: should` rules, report deviations explicitly instead of silently continuing.
