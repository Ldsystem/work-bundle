---
name: wb-integrity-check
description: "Agent-owned work-bundle integrity validation helper. Uses one bounded CLI for report lifecycle operations only."
---

# wb-integrity-check

This skill preserves agent-owned integrity judgment. The CLI is a deterministic helper for report artifacts and status bookkeeping only.

## Authority Sources

- `rules/integrity-check/index.yaml`
- `references/integrity-check/integrity-check-template.md`

Before running integrity-check workflow, load `rules/integrity-check/index.yaml` and apply every `severity: must` rule as mandatory execution constraints.

## Command Surface

Direct CLI:

- `python3 scripts/integrity_check_report.py new --template references/integrity-check/integrity-check-template.md --output-root <dir> --title <title>`
- `python3 scripts/integrity_check_report.py add-issue --report <report.md> --severity <level> --type <kind> --summary <text> --recommended-fix <text> --evidence <text> [--evidence <text>]`
- `python3 scripts/integrity_check_report.py update-status --report <report.md> --issue-id WBI-<num> --status fixed|dismissed|converted|superseded --reason <text> [--evidence <text>]`
- `python3 scripts/integrity_check_report.py summarize-status --report <report.md> [--output <status.json>]`
- `python3 scripts/integrity_check_report.py archive-report --report <report.md> --archive-root <dir> [--allow-open] [--move]`
- `python3 scripts/integrity_check_report.py validate-report --report <report.md>`

Unified dispatcher route:

- `python3 scripts/wb.py integrity-check-report <subcommand> ...`

## Boundary Contract

- Integrity findings, severity, ownership, and recommendation authority remain agent/user owned.
- Helper CLI may report boundary risks as evidence signals.
- Final accept/reject/escalation decision is always human-owned.
- Runtime enforcement authority comes from `rules/integrity-check/*.yaml` and must be treated as `must` scope policy.
- CLI does not inspect bundle policy correctness, does not classify integrity correctness as authority, and does not execute arbitrary project code.
- `validate-report` checks structure only and rejects finding-correctness validation mode.

## Expected Outputs

- Report markdown generated from template.
- Issue sidecar: `<report>.issues.json`
- Status sidecar: `<report-stem>.status.json`
- JSON command output with `final_decision_owner: human`.

