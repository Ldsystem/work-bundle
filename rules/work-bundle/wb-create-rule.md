---
id: wb-create-rule
applies_when:
  - user requests creation, update, migration, or validation of work-bundle runtime rules
  - agent creates or edits Markdown rule files under rules/
  - agent registers or syncs rules in rules/index.yaml
  - agent creates, validates, registers, or syncs toolkit, global user, or project rule-store scopes
enforcement: must
load: conditional
requires: []
---

# Create Rule

## Purpose

Summarize the enforceable contract for creating, migrating, and validating work-bundle runtime rules. Full agent authority lives in `skills/wb-create-rule/SKILL.md`; this rule mirrors key placement, rule-store scope, authority, and validation boundaries for index-first loading.

## Must

- Resolve rule-store scope before rule work: `toolkit` → `$work_bundle_root/rules/`, `global` → `$work_bundle_config_root/rules/`, `project` → `$workspace_root/.work-bundle/rules/`, or explicit root compatibility mode.
- Treat rule-store scope separately from rule area directories (`work-bundle/`, `keep-summarizing/`, `orchestration/`, `integrity-check/`).
- Store scoped rules under `<rules-root>/<scope>/<rule-id>.md` using the prefix map (`wb-` → `work-bundle/`, `ks-` → `keep-summarizing/`, `orch-` → `orchestration/`, `rule-integrity-check-` → `integrity-check/`).
- Store cross-cutting rules at `<rules-root>/<rule-id>.md` directly under the selected rules root; do not use a `global/` area directory.
- Use canonical front matter: `id`, `applies_when`, `enforcement`, `load`, `requires`.
- Include body sections: Purpose, Must, Must Not, Validation, On Violation.
- Register every rule in the selected rules root's `index.yaml` with metadata mirroring front matter.
- Keep rules under 500 lines and self-contained in the rule body.
- Run `python3 scripts/wb.py create-rules --scope <toolkit|global|project>` to sync the index after changes, or use explicit-root compatibility mode when required.
- Run `python3 scripts/wb.py validate-rules --scope <toolkit|global|project>` for mechanical checks, or use explicit-root compatibility mode when required.
- Enforce the toolkit write boundary: do not mutate `$work_bundle_root/rules/**` unless `$workspace_root == $work_bundle_root`.
- Never pass area subdirectories such as `rules/work-bundle/` to `create-rules` or `validate-rules`.
- Inspect `applies_when` semantically for concrete, actionable conditions before registration.
- Apply the Trigger Clarity Principle to rule triggers and rule prose: name the user-visible or workflow-visible signal before describing rule lookup, selection, applicability, or application.
- Load mechanical catalogs from `references/wb-create-rule-validation.yaml` when verifying placement and fields.

## Must Not

- Do not cite paths outside the selected rule-store root, `skills/wb-create-rule/SKILL.md`, `references/wb-create-rule-validation.yaml`, or `scripts/wb.py` as rule authority.
- Do not use legacy front matter fields: `scope`, `type`, `blocks`, `severity`, `status`, or `source_authority`.
- Do not create `.mdc` rule files or a `global/` area directory.
- Do not run `create-rules` or `validate-rules` against scope subdirectories; that creates incorrect nested indexes.
- Do not create, edit, delete, migrate, or index toolkit rules from a non-toolkit project root.
- Do not rely on scripts to judge `applies_when` meaning; scripts check presence and format only.
- Do not register documentation-only notes as enforceable rules.
- Do not use `before rule selection`, `when selecting rules`, `when needed`, `when relevant`, or similar phrasing as the only trigger for rule consideration.
- Do not write instructions that require the agent to already know a rule is relevant before the instruction explains the observable signal used to detect relevance.

## Validation

- Verify path placement against `references/wb-create-rule-validation.yaml` `id_prefix_scope_map` and `path_rules`.
- Agent rejects vague `applies_when` tokens (`when relevant`, `if needed`, `as appropriate`, and similar).
- Agent confirms trigger prose names an observable user or workflow signal before rule lookup, selection, applicability, or application language.
- Mechanical validation via `python3 scripts/wb.py validate-rules --scope <toolkit|global|project>` or explicit-root compatibility mode confirms required keys, prohibited fields, index sync, and line limits.

## On Violation

Stop rule creation or migration, report the violated field, section, or vague condition, and make the minimal correction before registering the rule. For `enforcement: should` rules, report deviations explicitly.
