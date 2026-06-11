---
name: wb-create-rule
description: 'Create, update, migrate, and validate Markdown work-bundle runtime rules under rules/ using the index-first rule contract. Canonical work-bundle skill name: wb-create-rule.'
---

# wb-create-rule

Use when creating, updating, migrating, or validating work-bundle rule files.

## Rule Contract

Rules are Markdown files under `rules/` with YAML front matter and an enforceable body.

Required front matter:

```yaml
---
id: <rule-id>
applies_when:
  - <condition>
enforcement: <must|should>
load: <always|conditional|manual>
requires: []
---
```

Required body sections:

```markdown
# <Rule Title>

## Purpose

## Must

## Must Not

## Validation

## On Violation
```

## Commands

Use the unified work-bundle dispatcher:

- Create or refresh rules: `python3 scripts/wb.py create-rules rules`
- Validate rules: `python3 scripts/wb.py validate-rules rules`

## Must

- Create one rule per enforceable contract.
- Keep each rule concise and under 500 lines.
- Put activation logic in `applies_when`.
- Use `enforcement` to define mandatory or expected force.
- Register every rule in `rules/index.yaml`.
- Keep rule front matter and index metadata synchronized.
- Prefer `load: conditional` unless startup loading is explicitly required.

## Must Not

- Do not use legacy front matter fields: `scope`, `type`, `blocks`, `severity`, `status`, or `source_authority`.
- Do not register documentation-only notes as rules.
- Do not create broad rules that require agents to read unrelated source documents.
- Do not create `.mdc` rule files.

## Validation

Before completing rule work, verify the file exists under the correct `rules/` subdirectory, front matter is valid, required body sections exist, the index entry mirrors front matter, and no prohibited legacy fields are present.

## On Violation

Stop rule creation or migration, report the violated field or section, and make the minimal correction before registering the rule.
