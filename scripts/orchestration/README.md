# Orchestration Scripts

Implementation modules in this directory are the manual maintenance surface for orchestration helpers.

The top-level `../orch.py` entrypoint is the public command surface. Implementation is split by current artifact area (`specs.py`, `plans.py`, `handoffs.py`, `review_runtime.py`, `documents.py`, `doctor.py`), with `dispatcher.py` only wiring commands. Despite its historical module name, `handoffs.py` owns canonical `executor-result-v2` records; it does not create or read legacy handoff artifacts.

Command examples:

The examples use the macOS/Linux `python3` launcher. On Windows, use `py -3.13` or a resolved `python` executable instead.

```bash
python3 scripts/orch.py write-spec --title "<title>" --purpose "<purpose>" --component "<component>" --content-file <file>
python3 scripts/orch.py write-plan --title "<title>" --purpose "<purpose>" --component "<component>" --content-file <file>
python3 scripts/orch.py write-executor-result --id <result-id> --plan-id <plan-id> --task-id <task-id> --content-file <file>
python3 scripts/orch.py write-implementation-review --id <review-id> --plan-id <plan-id> --task-id <task-id> --source-root <repository> --content-file <file>
python3 scripts/orch.py write-final-workflow-review --id <final-id> --plan-id <plan-id> --content-file <file>
python3 scripts/orch.py build-implementation-review-candidate --source-root <repository> --kind commit --candidate-commit <40-character-commit> --changed-path <path>
python3 scripts/orch.py build-implementation-review-candidate --source-root <repository> --kind worktree --base-commit <40-character-baseline> --changed-path <path>
python3 scripts/orch.py doctor
```

Orchestration artifacts resolve from the containing `workspace_root`, including when invoked inside a nested member. Repository inspection, tests, preflight, commits, and CodeGraph remain scoped to each selected member `project_root`. Execution consumes carried specification, plan, and task context and never reads `.work-bundle/knowledge/` or credential values directly.

Current canonical outputs are stored by family:

- executor results: `.work-bundle/orchestration/result/executor/`
- accepted task results: `.work-bundle/orchestration/result/accepted/`
- implementation reviews: `.work-bundle/orchestration/review/implementation/`
- final workflow reviews: `.work-bundle/orchestration/review/final/`

Writers enforce schema, identity, bindings, and canonical location before mutation. The controller's semantic decision after independent advisory review owns product acceptance; indexes and doctor output are regenerable structural observations.

Use `build-implementation-review-candidate`, `write-implementation-review`, `write-accepted-task-result`, and `write-final-workflow-review` for the direct review path. Use `finalize-reviewed-plan` only after the required canonical review artifacts exist.

Commit mode requires `--candidate-commit` (`candidate_commit` in the builder API) and hashes that commit's bytes even when the worktree differs. Worktree mode requires `--base-commit` (`base_commit` in the API), hashes current files, and uses the baseline to admit deleted paths. These inputs are mutually exclusive; `--base-commit` is unsupported as a commit-mode alias. The existing persisted `target.base_commit` field remains the selected commit for commit mode or the baseline for worktree mode, preserving supported active v2/v3 review reads.

Result/review `--id` values follow the current catalog shapes: `result-[a-z0-9][a-z0-9-]*`, `review-[a-z0-9][a-z0-9-]*`, `accepted-[a-z0-9][a-z0-9-]*`, and `final-[a-z0-9][a-z0-9-]*`. These are regular expressions: the prefix is followed by a lowercase letter or digit, then zero or more lowercase letters, digits, or hyphens. For example, `result-1`, `review-task`, `accepted-task`, and `final-plan` are valid; no date or revision suffix is required.

## Semantic-input scaffolds

`scaffold` prints JSON to stdout without writing canonical artifacts or rebuilding indexes:

```bash
python3 scripts/orch.py scaffold --family task-v3 --plan-id plan-example --phase-id phase-example --task-id task-new --source-id REQ-001
python3 scripts/orch.py scaffold --family plan-v1 --source-spec-id spec-example
python3 scripts/orch.py scaffold --family specification-v1
```

The explicit supported scope is `specification-v1`, `plan-v1`, `phase-v2`, `task-v3`, `executor-result-v2`, `implementation-review-v3`, `accepted-task-result-v2`, and `final-workflow-review-v1`. Catalog additions do not expand it automatically.

The envelope separates `invocation_inputs` (options for `writer_command`), `semantic_input` (the writer's editable payload), `resolved_context` (read-only canonical reference facts and verified specification source prose), and `script_owned_fields` (fields rejected by that writer's semantic reader). Fill every `<agent-authored-...>` placeholder explicitly, including placeholders for complete arrays/objects, verdicts, and acceptance decisions. Use only the filled `semantic_input` as the writer's JSON/YAML content file. For specifications, use it as Markdown front matter with the filled `semantic_body`. Do not pass the envelope or resolved context as semantic input.

The implementation-review scaffold exposes the unchanged `target` shape with editable `kind`, `base_commit`, `manifest`, and `sha256` placeholders. Supply the exact candidate target; scaffolding does not compute it or generate a product review verdict or acceptance decision.

Planning and result/review shells require an active canonical parent plan; a new plan requires an active verified `--source-spec-id`. A task also requires its existing parent `--phase-id`. Executor and accepted-result shells require an existing canonical `--task-id`; implementation-review accepts one for task review or omits it for integrated review. IDs supplied for new target artifacts are validated mechanically and may otherwise remain placeholders. Phase/task writers use `--phase-id`/`--task-id`, and their names come through `--title`. Repeat `--source-id` to resolve selected named units from the verified source specification. Unknown source IDs, conflicting/unsafe parent or target bindings, and options unsupported by the selected writer refuse before output. The command does not choose decomposition, obligation prose, qualification, review verdicts, or acceptance.
