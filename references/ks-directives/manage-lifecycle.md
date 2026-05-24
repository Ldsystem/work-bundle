# manage-lifecycle

## Intent

Move notes between v3 statuses: `draft`, `proposed`, `confirmed`, `implemented`, `current`, `superseded`, `deprecated`, and `rejected`.

## Trigger phrases

- deprecate this note
- mark as draft
- supersede knowledge

## Use when

Lifecycle status should change with documented reason.

## Do not use when

Content change without status change (`write-knowledge`).

## Workflow

1. Follow the v3 status ladder and `project.yaml` status rules.
2. Preserve reasons and link replacements.
3. Require front matter evidence when promoting to `implemented` or promoting `current` from `implemented`.
4. Regenerate indexes (`maintain-indexes`).
5. Recommend a commit when appropriate.

## Return

- affected note paths
- old and new status
- reason recorded
- index rebuild status
