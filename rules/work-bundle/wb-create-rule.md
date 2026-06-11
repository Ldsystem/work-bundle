---
id: wb-create-rule
applies_when:
  - user requests creation, update, migration, or validation of work-bundle runtime rules
  - agent creates or edits Markdown rule files under rules/
  - agent registers or syncs rules in rules/index.yaml
enforcement: must
load: conditional
requires: []
---

# Create Rule

## Purpose

Summarize the enforceable contract for creating, migrating, and validating work-bundle runtime rules. Full agent authority lives in `skills/wb-create-rule/SKILL.md`; this rule mirrors key placement, authority, and validation boundaries for index-first loading.

## Must

- Store scoped rules under `rules/<scope>/<rule-id>.md` using the prefix map (`wb-` → `work-bundle/`, `ks-` → `keep-summarizing/`, `orch-` → `orchestration/`, `rule-integrity-check-` → `integrity-check/`).
- Store cross-cutting rules at `rules/<rule-id>.md` directly under `rules/`; do not use `rules/global/`.
- Use canonical front matter: `id`, `applies_when`, `enforcement`, `load`, `requires`.
- Include body sections: Purpose, Must, Must Not, Validation, On Violation.
- Register every rule in `rules/index.yaml` with metadata mirroring front matter.
- Keep rules under 500 lines and self-contained in the rule body.
- Run `python3 scripts/wb.py create-rules <rules-root>` to sync the index after changes.
- Run `python3 scripts/wb.py validate-rules <rules-root>` for mechanical checks on touched paths.
- Inspect `applies_when` semantically for concrete, actionable conditions before registration.
- Load mechanical catalogs from `references/wb-create-rule-validation.yaml` when verifying placement and fields.

## Must Not

- Do not cite paths outside the git repository as authority.
- Do not use legacy front matter fields: `scope`, `type`, `blocks`, `severity`, `status`, or `source_authority`.
- Do not create `.mdc` rule files or a `rules/global/` directory.
- Do not rely on scripts to judge `applies_when` meaning; scripts check presence and format only.
- Do not register documentation-only notes as enforceable rules.

## Validation

- Verify path placement against `references/wb-create-rule-validation.yaml` `id_prefix_scope_map` and `path_rules`.
- Agent rejects vague `applies_when` tokens (`when relevant`, `if needed`, `as appropriate`, and similar).
- Mechanical validation via `python3 scripts/wb.py validate-rules <rules-root>` confirms required keys, prohibited fields, index sync, and line limits.

## On Violation

Stop rule creation or migration, report the violated field, section, or vague condition, and make the minimal correction before registering the rule. For `enforcement: should` rules, report deviations explicitly.
