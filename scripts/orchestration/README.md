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

For deterministic source-bound checks, declare `evidence_reuse: {mode: deterministic}` in task validation. After establishing the task execution binding, run `python3 scripts/orch.py observe-task-validation --project-root <workspace> --task <task>` to record actual results before writing the handoff. `validate-executor-result`, review packaging, and completion checks reuse eligible successful evidence instead of launching the observation again. Running a command manually does not seed provenance.

`evaluation_identity.validation_source_identity` computes the conservative material source tree and index identity, including dirty/untracked content and declared ignored task inputs. It separates generated WorkBundle runtime/handoff/review/log evidence from source inputs. Other output-only paths must be explicitly declared; they cannot overlap declared read/dependency inputs. Source trees use Git-compatible blob/tree hashes without writing Git objects or changing the index. This is content-based evidence, so exact A → B → A restoration can reuse a fresh result. Explicit provenance revocation still advances the existing epoch.

`completion_provenance.observe_validation` projects source, semantic check fields (ID/kind, command/mechanism, expected/acceptable results, invariant IDs and digest), task authority, runner/oracle, environment and freshness into `ObservationIdentityV1`. It uses the same `.work-bundle/runtime/completion-provenance` store that owns execution bindings; there is no separate cache store or adapter module. Old adapter records are not adopted as acceptance evidence.

Environment identity is OS, architecture, interpreter implementation/version/binary digest, declared `dependency_files`, `profile`, and only named `environment_inputs`. Values and command output are persisted only as digests. Cwd and execution/task binding remain distinct, so local evidence cannot accidentally satisfy GitHub Ubuntu/macOS acceptance. Use `include_head: true` for exact-release-commit claims. The profile must accurately cover the actual runner; undeclared mutable tools, services or external inputs make deterministic reuse ineligible.

Deterministic declarations default to 3600 seconds; undeclared/live checks default to fresh execution. Live checks may declare `max_age_seconds` explicitly (0–86400); skipped/failed observations are not positive reusable evidence. Legacy `reuse_seconds` is still accepted with its HEAD-bound semantics. Unsupported links/submodules or protected source inputs fall back to fresh observation. See the task contract for policy fields.

Every acceptance call still checks handoff/task/plan identity, binding, write scope, result shape, knowledge disposition, evidence closure, authorization and Git-neutrality. Fingerprint exclusions do not grant write authority. This is not per-feature dependency pruning, and it does not replace platform-specific release/CI gates.
