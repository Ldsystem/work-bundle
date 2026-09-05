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

## Reusing validation observations

For deterministic source-bound process checks, declare `reuse_seconds` in task validation (0 by default; maximum 86400). After establishing the task execution binding, run `python3 scripts/orch.py observe-task-validation --project-root <workspace> --task <task>` to execute through the harness and print actual results before writing the handoff. `validate-executor-result`, review packaging, and completion checks reuse an eligible successful observation instead of launching its command again. Running a command manually does not seed provenance.

Reuse compares repository HEAD/tree/index and dirty/untracked content, compiled task/check, harness implementation, environment fingerprint, bound execution/task, and expiry. Observed state transitions advance the native mutation epoch, including a later revert. Environment values and process output are stored only as digests. Handoff summary edits do not invalidate observations. The existing lock-protected completion provenance store owns the records; no executor-authored receipt is trusted. Failures and source-mutating checks do not create reusable success records.

This is conservative same-state reuse, not inferred per-feature dependency pruning. Keep live/remote checks and checks dependent on ignored or mutable external inputs at `reuse_seconds: 0`. All acceptance structure, scope and Git-neutrality checks remain mandatory even on a cache hit. Full release gates are not required merely to validate a handoff when its eligible observations remain current.
