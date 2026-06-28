# Work-Bundle Scripts

Implementation modules in this directory are the manual maintenance surface for work-bundle helpers.

The top-level `../wb.py` entrypoint remains for compatibility with existing agent instructions. Implementation is split by skill area (`rules.py`, `project.py`, `doctor.py`, `metadata_profile.py`, `skill_registry.py`, `role_context.py`, `integrity.py`), with `dispatcher.py` only wiring commands.

Command examples:

```bash
python3 scripts/wb.py initialize-project <project-root>
python3 scripts/wb.py create-rules rules
python3 scripts/wb.py validate-rules rules
python3 scripts/wb.py violation-ensure-store
python3 scripts/wb.py violation-create-evidence --status active --short-description <slug> --deviation <text> --occurrence <text> --evidence <path-or-surface> --severity p5
python3 scripts/wb.py violation-build-index
python3 scripts/wb.py violation-write-index
python3 scripts/wb.py violation-archive-evidence <evidence-id-or-path> --action completed
python3 scripts/wb.py integrity-check-report new --template references/integrity-check/integrity-check-template.md --output-root /tmp/reports --title check
```

Use the canonical `rules/` directory for `create-rules` and `validate-rules`. Scope subdirectories such as `rules/work-bundle/` are rejected because they create incorrect nested indexes.
