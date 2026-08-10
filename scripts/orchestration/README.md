# Orchestration Scripts

Implementation modules in this directory are the manual maintenance surface for orchestration helpers.

The top-level `../orch.py` entrypoint remains for compatibility with existing agent instructions. Implementation is split by artifact area (`specs.py`, `plans.py`, `handoffs.py`, `documents.py`, `doctor.py`), with `dispatcher.py` only wiring commands.

Command examples:

```bash
python3 scripts/orch.py write-spec --title "<title>" --purpose "<purpose>" --component "<component>" --content-file <file>
python3 scripts/orch.py write-plan --title "<title>" --purpose "<purpose>" --component "<component>" --content-file <file>
python3 scripts/orch.py doctor
```

Orchestration artifacts resolve from the containing `workspace_root`, including when invoked inside a nested member. Repository inspection, tests, preflight, commits, and CodeGraph remain scoped to each selected member `project_root`. Execution consumes carried spec/plan/task/handoff context and never reads `.work-bundle/knowledge/` or credential values directly.
