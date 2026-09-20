# Orchestration Scripts

Implementation modules in this directory are the manual maintenance surface for orchestration helpers.

The top-level `../orch.py` entrypoint is the public command surface. Implementation is split by current artifact area (`specs.py`, `plans.py`, `handoffs.py`, `review_runtime.py`, `documents.py`, `doctor.py`), with `dispatcher.py` only wiring commands. Despite its historical module name, `handoffs.py` owns canonical `executor-result-v1` records; it does not create or read legacy handoff artifacts.

Command examples:

The examples use the macOS/Linux `python3` launcher. On Windows, use `py -3.13` or a resolved `python` executable instead.

```bash
python3 scripts/orch.py write-spec --title "<title>" --purpose "<purpose>" --component "<component>" --content-file <file>
python3 scripts/orch.py write-plan --title "<title>" --purpose "<purpose>" --component "<component>" --content-file <file>
python3 scripts/orch.py write-executor-result --id <result-id> --plan-id <plan-id> --task-id <task-id> --content-file <file>
python3 scripts/orch.py write-implementation-review --id <review-id> --plan-id <plan-id> --task-id <task-id> --source-root <repository> --content-file <file>
python3 scripts/orch.py write-final-workflow-review --id <review-id> --plan-id <plan-id> --content-file <file>
python3 scripts/orch.py doctor
```

Orchestration artifacts resolve from the containing `workspace_root`, including when invoked inside a nested member. Repository inspection, tests, preflight, commits, and CodeGraph remain scoped to each selected member `project_root`. Execution consumes carried specification, plan, and task context and never reads `.work-bundle/knowledge/` or credential values directly.

Current canonical outputs are stored by family:

- executor results: `.work-bundle/orchestration/result/executor/`
- accepted task results: `.work-bundle/orchestration/result/accepted/`
- implementation reviews: `.work-bundle/orchestration/review/implementation/`
- final workflow reviews: `.work-bundle/orchestration/review/final/`

Writers enforce schema, identity, bindings, and canonical location before mutation. Direct semantic review remains the authority for product correctness; indexes and doctor output are regenerable structural observations, not acceptance verdicts.

Use `build-implementation-review-candidate`, `write-implementation-review`, `write-accepted-task-result`, and `write-final-workflow-review` for the direct review path. Use `finalize-reviewed-plan` only after the required canonical review artifacts exist.
