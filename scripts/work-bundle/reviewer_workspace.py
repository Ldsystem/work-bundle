from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import uuid


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SCOPES = frozenset({"source", "control"})
NETWORK_STATES = frozenset({"denied"})
VALIDATOR_KINDS = frozenset({"json", "sha256", "command"})
TERMINAL_VERDICTS = frozenset({"accepted", "repair", "blocked"})
NATIVE_DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "code_mode", "code_mode_host", "apps", "hooks",
    "browser_use", "browser_use_external", "browser_use_full_cdp_access", "computer_use",
    "in_app_browser", "image_generation", "multi_agent", "view_image", "workspace_dependencies",
    "tool_suggest", "skill_search", "sleep_tool", "goals", "memories", "remote_plugin", "recommended_plugins",
)
NATIVE_ISOLATION = {
    "mechanism": "native-host-read-only", "network": "model-transport",
    "write_scope": "read-only", "context": "fresh-native-host-context-with-explicit-evidence",
    "host_skill_catalog": "may-be-present",
    "tools": "disabled-and-no-observed-activity", "os_process_isolation": False,
}
NATIVE_REVIEW_REQUEST_MAX_CHARS = 1_048_576


def _structured_evidence(content: str) -> dict[str, object] | None:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        try:
            value = _review_runtime().parse_yaml_subset(content)
        except (SystemExit, ValueError, TypeError):
            return None
    return value if isinstance(value, dict) else None


def _integrated_change_manifest(
    packet: dict[str, object], evidence: list[dict[str, object]],
) -> tuple[dict[str, object], set[str], dict[str, str] | None] | None:
    context = packet.get("stage_review_context")
    if not isinstance(context, dict) or context.get("stage") != "integrated_implementation":
        return None
    target = context.get("target_identity")
    target_tree = target.get("source_tree") if isinstance(target, dict) else None
    candidates: list[tuple[dict[str, object], set[str], dict[str, str] | None]] = []
    for item in evidence:
        if not str(item.get("locator") or "").startswith("control:"):
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        value = _structured_evidence(content)
        if not isinstance(value, dict):
            continue
        baseline = value.get("baseline")
        endpoint = value.get("endpoint")
        comparison = value.get("comparison")
        if not all(isinstance(part, dict) for part in (baseline, endpoint, comparison)):
            continue
        paths = comparison.get("paths")
        if endpoint.get("tree") != target_tree or not isinstance(paths, list):
            continue
        exact_diff = comparison.get("exact_diff")
        normalized_diff = None
        if exact_diff is not None:
            if (
                not isinstance(exact_diff, dict)
                or set(exact_diff) != {"command", "locator", "sha256"}
                or not str(exact_diff.get("locator") or "").startswith("control:")
                or not re.fullmatch(r"[0-9a-f]{64}", str(exact_diff.get("sha256") or ""))
                or not isinstance(exact_diff.get("command"), str)
            ):
                raise ReviewerWorkspaceError("WB_REVIEW_CHANGE_MANIFEST_INVALID")
            normalized_diff = {
                "command": exact_diff["command"],
                "locator": exact_diff["locator"],
                "sha256": exact_diff["sha256"],
            }
        locators: set[str] = set()
        valid = True
        for raw in paths:
            if not isinstance(raw, dict) or set(raw) != {"status", "path"}:
                valid = False
                break
            path = Path(str(raw.get("path") or ""))
            if (
                raw.get("status") not in {"added", "modified", "deleted"}
                or path.is_absolute()
                or not path.parts
                or ".." in path.parts
            ):
                valid = False
                break
            if raw["status"] != "deleted":
                locators.add("source:" + path.as_posix())
        if valid:
            candidates.append((value, locators, normalized_diff))
    if len(candidates) > 1:
        raise ReviewerWorkspaceError("WB_REVIEW_CHANGE_MANIFEST_AMBIGUOUS")
    return candidates[0] if candidates else None


def _stage_evidence_roles(packet: dict[str, object]) -> dict[str, str]:
    manifest = packet.get("stage_evidence_manifest")
    entries = manifest.get("entries") if isinstance(manifest, dict) else []
    return {
        str(item.get("locator") or ""): str(item.get("role") or "")
        for item in entries
        if isinstance(item, dict)
    }


def _controller_only_artifact_locators(
    packet: dict[str, object], evidence: list[dict[str, object]],
) -> set[str]:
    context = packet.get("stage_review_context")
    if not isinstance(context, dict) or context.get("stage") != "integrated_implementation":
        return set()
    roles = _stage_evidence_roles(packet)
    result: set[str] = set()
    for item in evidence:
        locator = str(item.get("locator") or "")
        if roles.get(locator) in {"accepted_task_result", "validation_observation"}:
            result.add(locator)
            continue
        if "/handoff/" in locator:
            result.add(locator)
            continue
        content = item.get("content")
        value = _structured_evidence(content) if isinstance(content, str) else None
        schema = str(value.get("schema") or "") if isinstance(value, dict) else ""
        if (
            isinstance(value, dict)
            and (
                value.get("type") == "executor-result"
                or "lifecycle" in schema
                or {"execution_id", "ownership", "accepted_result"}.issubset(value)
            )
        ):
            result.add(locator)
    return result


def _integrated_product_evidence(
    packet: dict[str, object], evidence: list[dict[str, object]],
) -> dict[str, object]:
    roles = _stage_evidence_roles(packet)
    accepted_results: list[dict[str, object]] = []
    accepted_observation_ids: set[str] = set()
    observation_stores: list[dict[str, object]] = []
    unresolved: list[object] = []
    for item in evidence:
        locator = str(item.get("locator") or "")
        content = item.get("content")
        value = _structured_evidence(content) if isinstance(content, str) else None
        if not isinstance(value, dict):
            continue
        if roles.get(locator) == "accepted_task_result":
            accepted = value.get("accepted_result")
            if not isinstance(accepted, dict):
                continue
            ids = [str(value) for value in accepted.get("validation_evidence_ids", [])]
            accepted_observation_ids.update(ids)
            accepted_results.append(
                {
                    "task_id": accepted.get("task_id"),
                    "accepted_source": accepted.get("accepted_source"),
                    "validation_evidence_ids": ids,
                    "review_id": accepted.get("review_id"),
                    "invalidation": accepted.get("invalidation"),
                }
            )
        elif roles.get(locator) == "validation_observation":
            observation_stores.append(value)
        elif locator not in _controller_only_artifact_locators(packet, [item]):
            unresolved.extend(value.get("unresolved", []) if isinstance(value.get("unresolved"), list) else [])
    observations = []
    for store in observation_stores:
        for item in store.get("observations", []):
            if not isinstance(item, dict) or item.get("observation_id") not in accepted_observation_ids:
                continue
            result = item.get("result") if isinstance(item.get("result"), dict) else {}
            observations.append(
                {
                    "observation_id": item.get("observation_id"),
                    "product_tree": item.get("product_tree"),
                    "command_digest": item.get("command_digest"),
                    "oracle_digest": item.get("oracle_digest"),
                    "result": {
                        key: result.get(key)
                        for key in (
                            "exit_code", "stdout_digest", "stderr_digest",
                            "started_at", "completed_at",
                        )
                    },
                }
            )
    return {
        "accepted_results": sorted(accepted_results, key=lambda item: str(item.get("task_id") or "")),
        "validation_observations": sorted(
            observations, key=lambda item: str(item.get("observation_id") or "")
        ),
        "unresolved_product_concerns": unresolved,
    }


def _native_review_artifacts(
    packet: dict[str, object], evidence: list[dict[str, object]],
) -> list[dict[str, object]]:
    manifest = _integrated_change_manifest(packet, evidence)
    artifacts = packet.get("artifacts")
    if not isinstance(artifacts, list) or manifest is None:
        return [item for item in artifacts or [] if isinstance(item, dict)]
    _, changed, exact_diff = manifest
    if exact_diff is not None:
        matching = [
            item
            for item in artifacts
            if isinstance(item, dict) and item.get("locator") == exact_diff["locator"]
        ]
        if len(matching) != 1 or matching[0].get("sha256") != exact_diff["sha256"]:
            raise ReviewerWorkspaceError("WB_REVIEW_CHANGE_MANIFEST_INVALID")
        changed = set()
    controller_only = _controller_only_artifact_locators(packet, evidence)
    return [
        item
        for item in artifacts
        if isinstance(item, dict)
        and item.get("locator") not in controller_only
        and (
            not str(item.get("locator") or "").startswith("source:")
            or item.get("locator") in changed
        )
    ]


def _validate_integrated_change_manifest(
    source_root: Path, packet: dict[str, object], evidence: list[dict[str, object]],
) -> None:
    selected = _integrated_change_manifest(packet, evidence)
    if selected is None:
        return
    manifest, changed, exact_diff = selected
    baseline = manifest["baseline"]
    endpoint = manifest["endpoint"]
    comparison = manifest["comparison"]
    baseline_head = str(baseline.get("head") or "")
    endpoint_head = str(endpoint.get("head") or "")
    expected_command = f"git diff --name-status {baseline_head}..{endpoint_head}"
    if comparison.get("command") != expected_command:
        raise ReviewerWorkspaceError("WB_REVIEW_CHANGE_MANIFEST_INVALID")
    head = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    tree = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", f"{endpoint_head}^{{tree}}"],
        capture_output=True,
        text=True,
    )
    ancestor = subprocess.run(
        ["git", "-C", str(source_root), "merge-base", "--is-ancestor", baseline_head, endpoint_head],
        capture_output=True,
    )
    diff = subprocess.run(
        ["git", "-C", str(source_root), "diff", "--name-status", baseline_head, endpoint_head],
        capture_output=True,
        text=True,
    )
    binary_diff = subprocess.run(
        ["git", "-C", str(source_root), "diff", "--binary", baseline_head, endpoint_head],
        capture_output=True,
    )
    status_names = {"A": "added", "M": "modified", "D": "deleted"}
    actual: list[dict[str, str]] = []
    if not diff.returncode:
        for row in diff.stdout.splitlines():
            columns = row.split("\t")
            if len(columns) != 2 or columns[0] not in status_names:
                raise ReviewerWorkspaceError("WB_REVIEW_CHANGE_MANIFEST_INVALID")
            actual.append({"status": status_names[columns[0]], "path": columns[1]})
    paths = comparison.get("paths")
    packet_locators = {
        str(item.get("locator") or "")
        for item in packet.get("artifacts", [])
        if isinstance(item, dict)
    }
    exact_diff_valid = True
    if exact_diff is not None:
        supplied = [item for item in evidence if item.get("locator") == exact_diff["locator"]]
        expected_binary_command = f"git diff --binary {baseline_head}..{endpoint_head}"
        exact_diff_valid = (
            len(supplied) == 1
            and exact_diff["command"] == expected_binary_command
            and not binary_diff.returncode
            and supplied[0].get("sha256") == exact_diff["sha256"]
            and hashlib.sha256(binary_diff.stdout).hexdigest() == exact_diff["sha256"]
            and str(supplied[0].get("content") or "").encode("utf-8") == binary_diff.stdout
        )
    if (
        head.returncode
        or head.stdout.strip() != endpoint_head
        or tree.returncode
        or tree.stdout.strip() != endpoint.get("tree")
        or ancestor.returncode
        or diff.returncode
        or comparison.get("path_count") != len(actual)
        or paths != actual
        or not changed.issubset(packet_locators)
        or not exact_diff_valid
    ):
        raise ReviewerWorkspaceError("WB_REVIEW_CHANGE_MANIFEST_INVALID")


def parse_native_reviewer_transcript(raw: str, stderr: str = "") -> tuple[str, dict[str, object]]:
    """Accept one completed fresh host turn, never a supplied verdict or tool run."""
    thread_id = None
    phase = "new"
    messages = []
    model_activity = False
    try:
        # The host can report failed tool dispatch only on stderr, with no JSONL
        # tool item. Unknown diagnostics are inadmissible, not evidence of silence.
        if any(line.strip() not in {"", "Reading additional input from stdin..."} for line in stderr.splitlines()):
            raise ValueError("unexpected host diagnostic")
        for line in raw.splitlines():
            event = json.loads(line)
            kind = event["type"]
            if kind == "thread.started" and phase == "new":
                thread_id = str(uuid.UUID(event["thread_id"]))
                phase = "ready"
            elif kind == "turn.started" and phase == "ready":
                phase = "running"
            elif kind == "item.completed" and phase in {"ready", "running"}:
                item = event["item"]
                if phase == "ready" and item["type"] == "error" and (
                    str(item.get("message", "")).startswith("Under-development features enabled: skip_host_skill_discovery.")
                    or str(item.get("message", "")).startswith("Code Mode is unavailable because code-mode host is disabled.")
                ):
                    continue
                if (phase == "running" and not model_activity and item["type"] == "error"
                        and item.get("message") == "Skill descriptions were shortened to fit the skills context budget. Codex can still see every skill, but some descriptions are shorter. Disable unused skills or plugins to leave more room for the rest."):
                    # Observed host initialization notice, not an attempted tool
                    # or model failure. Native catalog metadata may be present.
                    continue
                if phase != "running" or item["type"] not in {"agent_message", "reasoning"}:
                    raise ValueError("unexpected host activity")
                model_activity = True
                if item["type"] == "agent_message":
                    messages.append(item["text"])
            elif kind == "turn.completed" and phase == "running" and messages:
                phase = "complete"
            else:
                raise ValueError("unexpected host activity")
        if phase != "complete" or not thread_id:
            raise ValueError("incomplete host run")
        result = json.loads(messages[-1])
        if not isinstance(result, dict):
            raise ValueError("judgment must be an object")
        return thread_id, result
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ReviewerWorkspaceError("WB_REVIEW_NATIVE_TRANSCRIPT_INVALID") from error


def _native_reviewer_argv(executable: Path, workspace: Path, model: str) -> list[str]:
    return [str(executable), "exec", "--ignore-user-config", "--sandbox", "read-only", "--ephemeral",
            "--json", "--skip-git-repo-check", "-C", str(workspace), "-m", model,
            "-c", 'model_reasoning_effort="medium"', "-c", "project_doc_max_bytes=0",
            "-c", 'web_search="disabled"', "--enable", "skip_host_skill_discovery",
            *[part for feature in NATIVE_DISABLED_FEATURES for part in ("--disable", feature)], "-"]


def _run_native_process(workspace: Path, argv: list[str], request: str) -> subprocess.CompletedProcess[str]:
    # Desktop transport/session variables would reconnect the reviewer to author
    # capabilities even when native user config is suppressed. Never inherit them.
    environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(Path.home()),
                   "TMPDIR": str(workspace / "scratch")}
    if os.environ.get("CODEX_HOME"):
        environment["CODEX_HOME"] = os.environ["CODEX_HOME"]
    return subprocess.run(argv, cwd=workspace, env=environment, input=request, text=True,
                          capture_output=True, check=False, timeout=1800)


def _retain_native_diagnostics(runtime_root, run_id, review_id, argv, request_bytes, executable_digest, completed):
    """Keep actual transport evidence before admission; this is never a receipt."""
    directory = runtime_root / "diagnostics/reviewer-native" / run_id
    if not _inside(runtime_root, directory):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    directory.mkdir(parents=True, exist_ok=False)
    items = {
        "request.json": request_bytes,
        "stdout.jsonl": completed.stdout.encode(),
        "stderr.txt": completed.stderr.encode(),
        "launch.json": json.dumps({"argv": argv, "executable_sha256": executable_digest}, sort_keys=True).encode(),
    }
    items["capture.json"] = json.dumps({
        "schema": "reviewer-native-diagnostic-v1", "status": "unadmitted",
        "run_id": run_id, "review_id": review_id, "exit_code": completed.returncode,
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifacts": {name: _sha256_bytes(content) for name, content in items.items()},
    }, sort_keys=True).encode()
    for name, content in items.items():
        target = directory / name
        with target.open("xb") as stream:
            stream.write(content)
        target.chmod(0o400)
    return str(directory)


def _native_review_input(
    packet: dict[str, object], evidence: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    key = "task_review_context" if "task_review_context" in packet else "stage_review_context"
    context = packet[key]
    artifacts = packet["artifacts"]
    integrated = key == "stage_review_context" and context.get("stage") == "integrated_implementation"
    if integrated and evidence is not None:
        controller_only = _controller_only_artifact_locators(packet, evidence)
        artifacts = [
            item
            for item in artifacts
            if isinstance(item, dict) and item.get("locator") not in controller_only
        ]
        result = {
            "target_identity": context["target_identity"],
            "artifacts": artifacts,
            "product_evidence": _integrated_product_evidence(packet, evidence),
        }
        if context.get("repair_frontier") is not None:
            result["repair_frontier"] = context["repair_frontier"]
        return result
    if key == "task_review_context" or context.get("stage") == "integrated_implementation":
        return {"target_identity": context["target_identity"], "artifacts": artifacts}
    result = {
        "stage": context["stage"],
        "target_identity": context["target_identity"],
        "artifacts": artifacts,
    }
    if context.get("repair_frontier") is not None:
        result["repair_frontier"] = context["repair_frontier"]
    return result


def run_native_reviewer(workspace: Path, executable: Path, *, model: str, review_instructions: str) -> dict[str, object]:
    """Run a fresh native host judgment over explicit evidence; no plugin required.

    Native read-only policy is not the legacy OS process sandbox. The host may
    use its authentication/model transport; no author thread transport propagates,
    and any observed tool activity makes the result inadmissible.
    """
    executable = executable.expanduser().resolve()
    workspace = workspace.expanduser().resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ReviewerWorkspaceError(
            "WB_REVIEW_NATIVE_CAPABILITY_UNAVAILABLE",
            {"capability": "native_reviewer_executable"},
        )
    if not model:
        raise ReviewerWorkspaceError(
            "WB_REVIEW_NATIVE_CAPABILITY_UNAVAILABLE",
            {"capability": "native_reviewer_model"},
        )
    if not review_instructions.strip():
        raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID")
    packet, _ = _load_workspace(workspace)
    if not ("stage_review_context" in packet or "task_review_context" in packet):
        raise ReviewerWorkspaceError("WB_REVIEW_NATIVE_CONTEXT_REQUIRED")
    control_evidence = []
    for item in packet["artifacts"]:
        if str(item.get("locator") or "").startswith("control:"):
            content = _evidence_path(workspace, item["locator"]).read_bytes().decode("utf-8")
            control_evidence.append({**item, "content": content})
    controller_locators = _controller_only_artifact_locators(packet, control_evidence)
    controller_evidence = [
        item for item in control_evidence if item.get("locator") in controller_locators
    ]
    selected_artifacts = _native_review_artifacts(packet, control_evidence)
    evidence = []
    for item in selected_artifacts:
        # Text-mode reads normalize CRLF. The model input must preserve the exact
        # frozen bytes whose digest will be revalidated during publication.
        content = _evidence_path(workspace, item["locator"]).read_bytes().decode("utf-8")
        if _sha256_bytes(content.encode("utf-8")) != item["sha256"]:
            raise ReviewerWorkspaceError("WB_REVIEW_EVIDENCE_MUTATED")
        evidence.append({**item, "content": content})
    request = {
        "instructions": review_instructions,
        "review_input": _native_review_input(packet, control_evidence),
        "evidence": evidence,
    }
    if len(json.dumps(request, sort_keys=True, ensure_ascii=False)) > NATIVE_REVIEW_REQUEST_MAX_CHARS:
        raise ReviewerWorkspaceError(
            "WB_REVIEW_NATIVE_INPUT_TOO_LARGE",
            {"max_chars": NATIVE_REVIEW_REQUEST_MAX_CHARS},
        )
    argv = _native_reviewer_argv(executable, workspace, model)
    return _run_reviewer(
        workspace, argv, native_request=request,
        native_controller_evidence=controller_evidence,
    )


def _review_runtime():
    orchestration = Path(__file__).resolve().parents[1] / "orchestration"
    existing = sys.modules.get("review_runtime")
    if existing is not None:
        if Path(existing.__file__).resolve() != orchestration / "review_runtime.py":
            raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_MODULE_COLLISION")
        return existing
    spec = importlib.util.spec_from_file_location("review_runtime", orchestration / "review_runtime.py")
    module = importlib.util.module_from_spec(spec)
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(orchestration))
        sys.modules["review_runtime"] = module
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("review_runtime", None)
        raise
    finally:
        sys.path[:] = original_path
    return module


def _validate_stage_context(
    context: object, *, require_re_review_predecessor: bool = False,
) -> dict[str, object]:
    fields = {"stage", "target_identity", "target_locator", "agent_id", "capability", "execution_id", "evidence_mode"}
    repair_fields = {"review_mode", "review_target_kind", "repair_frontier", "review_reset"}
    allowed = {
        frozenset(fields),
        frozenset(fields | repair_fields),
        frozenset(fields | repair_fields | {"previous_review"}),
    }
    if not isinstance(context, dict) or frozenset(context) not in allowed:
        raise ReviewerWorkspaceError("WB_REVIEW_STAGE_CONTEXT_INVALID")
    if (context["stage"] not in {"specification", "plan", "integrated_implementation"}
            or context["capability"] not in {"standard", "judgment"}
            or context["evidence_mode"] not in {"direct_source", "reproducible_snapshot", "packet_only"}
            or not all(isinstance(context[key], str) and context[key] for key in ("agent_id", "execution_id"))):
        raise ReviewerWorkspaceError("WB_REVIEW_STAGE_CONTEXT_INVALID")
    _review_runtime()._target_identity(context["target_identity"])
    if repair_fields.issubset(context):
        try:
            mode = _review_runtime()._enum(context["review_mode"], _review_runtime().REVIEW_MODES, "review_mode")
            _review_runtime()._enum(context["review_target_kind"], _review_runtime().REVIEW_TARGET_KINDS, "review_target_kind")
            if mode == "repair":
                _review_runtime()._repair_frontier(context["repair_frontier"])
                if context["review_reset"] is not None:
                    raise ValueError("repair reset")
            elif context["repair_frontier"] is not None:
                raise ValueError("initial frontier")
            re_review = mode == "repair" or context["review_reset"] is not None
            if "previous_review" in context:
                previous = context.get("previous_review")
                if not isinstance(previous, dict) or "previous_review" in previous:
                    raise ValueError("re-review predecessor")
            if require_re_review_predecessor and re_review and "previous_review" not in context:
                raise ValueError("missing re-review predecessor")
            if not re_review and "previous_review" in context:
                raise ValueError("unexpected predecessor")
        except (ValueError, TypeError):
            raise ReviewerWorkspaceError("WB_REVIEW_STAGE_CONTEXT_INVALID") from None
    return context


def _validate_task_context(context: object) -> dict[str, object]:
    fields = {
        "target_identity", "agent_id", "capability", "execution_id", "evidence_mode",
        "review_mode", "review_target_kind", "repair_frontier", "review_reset",
    }
    allowed = {frozenset(fields), frozenset(fields | {"previous_review"})}
    if not isinstance(context, dict) or frozenset(context) not in allowed:
        raise ReviewerWorkspaceError("WB_REVIEW_TASK_CONTEXT_INVALID")
    if (
        context["review_target_kind"] != "task"
        or context["capability"] not in {"standard", "judgment"}
        or context["evidence_mode"] not in {"direct_source", "reproducible_snapshot", "packet_only"}
        or not all(isinstance(context[key], str) and context[key] for key in ("agent_id", "execution_id"))
    ):
        raise ReviewerWorkspaceError("WB_REVIEW_TASK_CONTEXT_INVALID")
    _review_runtime()._target_identity(context["target_identity"])
    try:
        mode = _review_runtime()._enum(context["review_mode"], _review_runtime().REVIEW_MODES, "review_mode")
        if mode == "repair":
            _review_runtime()._repair_frontier(context["repair_frontier"])
            if context["review_reset"] is not None:
                raise ValueError("repair reset")
        elif context["repair_frontier"] is not None:
            raise ValueError("initial frontier")
    except (ValueError, TypeError):
        raise ReviewerWorkspaceError("WB_REVIEW_TASK_CONTEXT_INVALID") from None
    return context


def _validate_task_source_identity(source_root: Path, context: dict[str, object]) -> None:
    identity = context["target_identity"]
    assert isinstance(identity, dict)
    head = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    tree = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD^{tree}"], capture_output=True, text=True
    )
    status = subprocess.run(
        ["git", "-C", str(source_root), "status", "--porcelain=v1"], capture_output=True, text=True
    )
    if (
        head.returncode or tree.returncode or status.returncode or status.stdout
        or head.stdout.strip() != identity.get("revision")
        or tree.stdout.strip() != identity.get("source_tree")
    ):
        raise ReviewerWorkspaceError("WB_REVIEW_TASK_TARGET_MISMATCH")


class ReviewerWorkspaceError(RuntimeError):
    def __init__(self, code: str, result: dict[str, object] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.result = result or {}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _sha256_bytes(encoded)


def _safe_id(value: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise ReviewerWorkspaceError("WB_REVIEW_ID_INVALID")
    return value


def _split_locator(locator: object) -> tuple[str, Path]:
    text = str(locator or "")
    scope, separator, raw_path = text.partition(":")
    if not separator or scope not in SCOPES:
        if scope == "host":
            raise ReviewerWorkspaceError(
                "WB_REVIEW_HOST_CONFIG_READ_DENIED", {"classification": "denied", "scope": "host"}
            )
        raise ReviewerWorkspaceError("WB_REVIEW_LOCATOR_INVALID", {"classification": "denied"})
    relative = Path(raw_path)
    if not raw_path or relative.is_absolute() or ".." in relative.parts or relative == Path("."):
        raise ReviewerWorkspaceError("WB_REVIEW_PATH_ESCAPE_DENIED", {"classification": "denied"})
    return scope, relative


def _inside(root: Path, candidate: Path) -> bool:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve(strict=False)
    return resolved_candidate == resolved_root or resolved_root in resolved_candidate.parents


def _normalized_roots(values: list[Path]) -> list[Path]:
    roots: list[Path] = []
    for value in values:
        root = Path(value).expanduser().resolve()
        if not root.exists() or root.is_symlink():
            raise ReviewerWorkspaceError("WB_REVIEW_PROTECTED_ROOT_INVALID")
        roots.append(root)
    if not roots:
        raise ReviewerWorkspaceError("WB_REVIEW_PROTECTED_ROOTS_REQUIRED")
    return roots


def _source_path(
    source_root: Path,
    control_root: Path,
    protected_roots: list[Path],
    locator: object,
) -> tuple[str, Path, Path]:
    scope, relative = _split_locator(locator)
    root = source_root if scope == "source" else control_root
    root = root.expanduser().resolve()
    candidate = root / relative
    if not _inside(root, candidate):
        raise ReviewerWorkspaceError("WB_REVIEW_PATH_ESCAPE_DENIED", {"classification": "denied"})
    if any(_inside(protected, candidate) for protected in protected_roots):
        raise ReviewerWorkspaceError(
            "WB_REVIEW_PROTECTED_READ_DENIED", {"classification": "denied", "scope": scope}
        )
    if not candidate.is_file() or candidate.is_symlink():
        raise ReviewerWorkspaceError("WB_REVIEW_DIRECT_EVIDENCE_MISSING", {"locator": f"{scope}:{relative.as_posix()}"})
    return scope, relative, candidate


def build_direct_evidence_packet(
    *,
    source_root: Path,
    control_root: Path,
    protected_roots: list[Path],
    artifacts: list[str],
    search_roots: list[str],
    validators: list[dict[str, object]],
    sentinels: list[str],
    network_state: str,
    stage_review_context: dict[str, object] | None = None,
    task_review_context: dict[str, object] | None = None,
) -> dict[str, object]:
    """Copy only named direct evidence into a location-free packet.

    Origin roots are used while compiling the packet and are deliberately not
    serialized. Review operations therefore have no path capability back to
    source, control-plane, registry, credentials, or host configuration.
    """
    if network_state not in NETWORK_STATES:
        raise ReviewerWorkspaceError("WB_REVIEW_NETWORK_STATE_REQUIRED")
    source_root = source_root.expanduser().resolve()
    control_root = control_root.expanduser().resolve()
    protected = _normalized_roots(protected_roots)
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for locator in artifacts:
        scope, relative, candidate = _source_path(source_root, control_root, protected, locator)
        normalized = f"{scope}:{relative.as_posix()}"
        if normalized in seen:
            raise ReviewerWorkspaceError("WB_REVIEW_ARTIFACT_DUPLICATE", {"locator": normalized})
        seen.add(normalized)
        content = candidate.read_bytes()
        records.append(
            {
                "locator": normalized,
                "sha256": _sha256_bytes(content),
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
        )
    normalized_search: list[str] = []
    for locator in search_roots:
        scope, relative = _split_locator(locator)
        root = source_root if scope == "source" else control_root
        candidate = root / relative
        if not _inside(root, candidate) or not candidate.is_dir() or candidate.is_symlink():
            raise ReviewerWorkspaceError("WB_REVIEW_SEARCH_ROOT_INVALID", {"locator": locator})
        if any(_inside(item, candidate) for item in protected):
            raise ReviewerWorkspaceError("WB_REVIEW_PROTECTED_READ_DENIED", {"classification": "denied"})
        normalized_search.append(f"{scope}:{relative.as_posix()}")
    normalized_validators: list[dict[str, object]] = []
    validator_ids: set[str] = set()
    for raw in validators:
        validator_id = _safe_id(str(raw.get("validator_id") or ""))
        kind = str(raw.get("kind") or "")
        locator = str(raw.get("artifact") or "")
        argv = raw.get("argv")
        command_valid = kind == "command" and isinstance(argv, list) and bool(argv) and all(
            isinstance(item, str) and item for item in argv
        )
        artifact_valid = kind in {"json", "sha256"} and locator in seen
        if validator_id in validator_ids or kind not in VALIDATOR_KINDS or not (command_valid or artifact_valid):
            raise ReviewerWorkspaceError("WB_REVIEW_VALIDATOR_INVALID", {"validator_id": validator_id})
        validator_ids.add(validator_id)
        normalized = {"validator_id": validator_id, "kind": kind}
        if command_valid:
            normalized["argv"] = list(argv)
        else:
            normalized["artifact"] = locator
        normalized_validators.append(normalized)
    sentinel_records: list[dict[str, str]] = []
    for locator in sentinels:
        scope, relative, candidate = _source_path(source_root, control_root, protected, locator)
        sentinel_records.append(
            {"locator": f"{scope}:{relative.as_posix()}", "sha256": _sha256_bytes(candidate.read_bytes())}
        )
    if stage_review_context is not None and task_review_context is not None:
        raise ReviewerWorkspaceError("WB_REVIEW_CONTEXT_AMBIGUOUS")
    stage_fields = {}
    if stage_review_context is not None:
        context = dict(
            _validate_stage_context(
                stage_review_context, require_re_review_predecessor=True
            )
        )
        manifest = _review_runtime().stage_evidence_manifest(control_root, source_root, context, records)
        # This runtime denies live source access. Only a complete frozen closure
        # is a reproducible snapshot; a caller's direct-source label grants nothing.
        context["evidence_mode"] = "packet_only" if manifest["missing"] else "reproducible_snapshot"
        stage_fields = {"stage_review_context": context, "stage_evidence_manifest": manifest}
    elif task_review_context is not None:
        context = dict(_validate_task_context(task_review_context))
        _validate_task_source_identity(source_root, context)
        stage_fields = {"task_review_context": context}
    return {
        "schema": "review-direct-evidence-packet-v1",
        **stage_fields,
        "artifacts": records,
        "search_roots": normalized_search,
        "validators": normalized_validators,
        "sentinels": sentinel_records,
        "network": {"state": network_state, "mechanism": "sandbox-exec-deny-network"},
        "policy_roots": {
            "source": str(source_root),
            "control": str(control_root),
            "protected": [str(item) for item in protected],
        },
    }


def _workspace_paths(runtime_root: Path, review_id: str) -> tuple[Path, Path]:
    root = runtime_root.expanduser().resolve()
    review_id = _safe_id(review_id)
    workspace = (root / "reviews" / review_id).resolve(strict=False)
    state = (root / ".state" / f"{review_id}.json").resolve(strict=False)
    if not _inside(root, workspace) or not _inside(root, state):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    return workspace, state


def _public_packet(packet: dict[str, object]) -> dict[str, object]:
    artifacts = packet.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID")
    result = {
        **{key: value for key, value in packet.items() if key != "policy_roots"},
        "artifacts": [
            {key: value for key, value in item.items() if key != "content_base64"}
            for item in artifacts
            if isinstance(item, dict)
        ],
    }
    for context_key in ("stage_review_context", "task_review_context"):
        context = result.get(context_key)
        if isinstance(context, dict) and "previous_review" in context:
            result[context_key] = {
                key: value for key, value in context.items() if key != "previous_review"
            }
    return result


def _sb_quote(path: Path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _runtime_read_roots() -> list[Path]:
    executable = Path(sys.executable).expanduser()
    candidates = {
        Path(value).expanduser().resolve()
        for value in (sys.prefix, sys.exec_prefix, sys.base_prefix, sys.base_exec_prefix)
        if value
    }
    candidates.add(executable.parent.parent.resolve())
    candidates.add(executable.resolve().parents[1])
    return sorted((path for path in candidates if path != Path("/")), key=str)


def _sandbox_profile(workspace: Path, policy: dict[str, object], validators: list[object]) -> str:
    roots = [Path(str(policy["source"])), Path(str(policy["control"]))]
    roots.extend(Path(str(value)) for value in policy.get("protected", []) if isinstance(value, str))
    denied_reads = " ".join(f"(subpath {_sb_quote(path.resolve())})" for path in roots)
    runtime_reads = " ".join(
        f"(subpath {_sb_quote(path)})" for path in _runtime_read_roots()
    )
    return "\n".join(
        [
            "(version 1)",
            "(deny default)",
            '(import "system.sb")',
            "(allow process*)",
            f"(allow file-read* (subpath {_sb_quote(workspace)}) {runtime_reads})",
            f"(deny file-read* {denied_reads})",
            f"(allow file-write* (subpath {_sb_quote(workspace / 'scratch')}))",
            "(allow file-write-data (literal \"/dev/null\"))",
            f"(deny file-write* {denied_reads})",
            "(deny network*)",
            "",
        ]
    )


def _path_identity_digest(path: Path) -> str:
    resolved = path.expanduser().resolve()
    if not resolved.exists() or resolved.is_symlink():
        raise ReviewerWorkspaceError("WB_REVIEW_POLICY_ROOT_INVALID")
    stat = resolved.stat()
    return _canonical_digest(
        {
            "path": str(resolved),
            "device": stat.st_dev,
            "inode": stat.st_ino,
            "mode": stat.st_mode,
            "kind": "directory" if resolved.is_dir() else "file",
        }
    )


def _root_identity_digests(source: Path, control: Path, protected: list[Path]) -> dict[str, object]:
    return {
        "source": _path_identity_digest(source),
        "control": _path_identity_digest(control),
        "protected": sorted(_path_identity_digest(path) for path in protected),
    }


def _artifact_digest(workspace: Path, packet: dict[str, object]) -> str:
    current: list[dict[str, str]] = []
    for item in packet.get("artifacts", []):
        if not isinstance(item, dict):
            raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID")
        locator = str(item.get("locator") or "")
        target = _evidence_path(workspace, locator)
        current.append({"locator": locator, "sha256": _sha256_bytes(target.read_bytes())})
    return _canonical_digest(current)


def _sentinel_digest(
    source_root: Path,
    control_root: Path,
    protected_roots: list[Path],
    sentinels: list[object],
) -> str:
    current: list[dict[str, str]] = []
    for item in sentinels:
        if not isinstance(item, dict):
            raise ReviewerWorkspaceError("WB_REVIEW_SENTINEL_INVALID")
        locator = str(item.get("locator") or "")
        _, _, target = _source_path(source_root, control_root, protected_roots, locator)
        current.append({"locator": locator, "sha256": _sha256_bytes(target.read_bytes())})
    return _canonical_digest(current)


def create_reviewer_workspace(
    runtime_root: Path,
    review_id: str,
    packet: dict[str, object],
    *,
    source_root: Path | None = None,
    control_root: Path | None = None,
    protected_roots: list[Path] | None = None,
) -> dict[str, object]:
    if packet.get("schema") != "review-direct-evidence-packet-v1":
        raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID")
    network = packet.get("network")
    if not isinstance(network, dict) or network.get("state") not in NETWORK_STATES:
        raise ReviewerWorkspaceError("WB_REVIEW_NETWORK_STATE_REQUIRED")
    workspace, state_path = _workspace_paths(runtime_root, review_id)
    if workspace.exists() or workspace.is_symlink() or state_path.exists():
        raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_COLLISION")
    artifacts = packet.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID")
    public_packet = _public_packet(packet)
    policy = packet.get("policy_roots")
    if not isinstance(policy, dict):
        raise ReviewerWorkspaceError("WB_REVIEW_PROTECTED_ROOTS_REQUIRED")
    effective_source = Path(str(source_root or policy.get("source") or "")).expanduser().resolve()
    effective_control = Path(str(control_root or policy.get("control") or "")).expanduser().resolve()
    effective_protected = _normalized_roots(
        protected_roots or [Path(str(value)) for value in policy.get("protected", []) if isinstance(value, str)]
    )
    if effective_source != Path(str(policy.get("source"))).resolve() or effective_control != Path(str(policy.get("control"))).resolve():
        raise ReviewerWorkspaceError("WB_REVIEW_POLICY_ROOT_MISMATCH")
    if "stage_review_context" in packet:
        context = _validate_stage_context(packet["stage_review_context"])
        # A caller cannot relabel stale copied bytes with a fresh target identity.
        for raw in artifacts:
            if not isinstance(raw, dict):
                raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID")
            _, _, current_artifact = _source_path(effective_source, effective_control, effective_protected, raw.get("locator"))
            if _sha256_bytes(current_artifact.read_bytes()) != raw.get("sha256"):
                raise ReviewerWorkspaceError("WB_REVIEW_STAGE_PACKET_STALE")
        scope, _, target = _source_path(effective_source, effective_control, effective_protected, context["target_locator"])
        if scope != "control" or context["target_locator"] not in {item.get("locator") for item in artifacts}:
            raise ReviewerWorkspaceError("WB_REVIEW_STAGE_TARGET_MISSING")
        current = _review_runtime().stage_target_identity(effective_control, str(context["stage"]), target,
                                                        source_root=effective_source)
        if current != context["target_identity"]:
            raise ReviewerWorkspaceError("WB_REVIEW_STAGE_TARGET_MISMATCH")
        manifest = _review_runtime().stage_evidence_manifest(effective_control, effective_source, context, artifacts)
        mode = "packet_only" if manifest["missing"] else "reproducible_snapshot"
        if packet.get("stage_evidence_manifest") != manifest or context["evidence_mode"] != mode:
            raise ReviewerWorkspaceError("WB_REVIEW_STAGE_EVIDENCE_MISMATCH")
        control_evidence = []
        for raw in artifacts:
            if not isinstance(raw, dict) or not str(raw.get("locator") or "").startswith("control:"):
                continue
            try:
                content = base64.b64decode(str(raw.get("content_base64") or ""), validate=True).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID") from None
            control_evidence.append(
                {
                    **{key: value for key, value in raw.items() if key != "content_base64"},
                    "content": content,
                }
            )
        _validate_integrated_change_manifest(effective_source, public_packet, control_evidence)
    elif "task_review_context" in packet:
        context = _validate_task_context(packet["task_review_context"])
        _validate_task_source_identity(effective_source, context)
    try:
        workspace.mkdir(parents=True)
        scope_digests: dict[str, list[str]] = {"source": [], "control": []}
        for raw in artifacts:
            if not isinstance(raw, dict):
                raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID")
            scope, relative = _split_locator(raw.get("locator"))
            try:
                content = base64.b64decode(str(raw.get("content_base64") or ""), validate=True)
            except (ValueError, TypeError):
                raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID") from None
            digest = _sha256_bytes(content)
            if digest != raw.get("sha256"):
                raise ReviewerWorkspaceError("WB_REVIEW_PACKET_DIGEST_MISMATCH")
            target = workspace / "evidence" / scope / relative
            if not _inside(workspace, target):
                raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o444)
            scope_digests[scope].append(f"{relative.as_posix()}\0{digest}")
        packet_path = workspace / "packet.json"
        packet_path.write_text(json.dumps(public_packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        packet_path.chmod(0o444)
        (workspace / "scratch").mkdir()
        sandbox_profile = workspace / "sandbox.sb"
        sandbox_profile.write_text(
            _sandbox_profile(workspace, policy, list(public_packet.get("validators", []))), encoding="utf-8"
        )
        sandbox_profile.chmod(0o444)
        evidence_digest = _artifact_digest(workspace, public_packet)
        sentinel_digest = _sentinel_digest(
            effective_source, effective_control, effective_protected, list(public_packet.get("sentinels", []))
        )
        previous_review_state = {}
        for context_key, state_key in (
            ("task_review_context", "task_review_previous_review"),
            ("stage_review_context", "stage_review_previous_review"),
        ):
            context = packet.get(context_key)
            if isinstance(context, dict) and "previous_review" in context:
                previous_review_state[state_key] = context["previous_review"]
        state = {
            "schema": "reviewer-workspace-state-v1",
            "owner": "work-bundle",
            "review_id": review_id,
            "workspace_token": f"reviews/{review_id}",
            "packet_sha256": _canonical_digest(public_packet),
            "source_evidence_digest": _sha256_bytes("\n".join(sorted(scope_digests["source"])).encode("utf-8")),
            "control_evidence_digest": _sha256_bytes("\n".join(sorted(scope_digests["control"])).encode("utf-8")),
            "network": dict(network),
            "sandbox": {"mechanism": "sandbox-exec", "profile_sha256": _sha256_bytes(sandbox_profile.read_bytes())},
            "evidence_digest": evidence_digest,
            "sentinel_digest": sentinel_digest,
            "root_identity_digests": _root_identity_digests(
                effective_source, effective_control, effective_protected
            ),
            "status": "active",
            **previous_review_state,
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        state_path.unlink(missing_ok=True)
        raise
    return {
        "status": "prepared",
        "workspace_path": str(workspace),
        "state_path": str(state_path),
        "network": network,
        "packet_sha256": state["packet_sha256"],
        "evidence_digest": state["evidence_digest"],
        "sentinel_digest": state["sentinel_digest"],
    }


def _load_workspace(workspace: Path) -> tuple[dict[str, object], dict[str, object]]:
    workspace = workspace.expanduser().resolve()
    packet_path = workspace / "packet.json"
    if not packet_path.is_file() or packet_path.is_symlink():
        raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID")
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID") from None
    artifacts = packet.get("artifacts")
    validators = packet.get("validators")
    if not isinstance(artifacts, list) or not isinstance(validators, list):
        raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID")
    by_locator = {str(item.get("locator")): item for item in artifacts if isinstance(item, dict)}
    by_validator = {str(item.get("validator_id")): item for item in validators if isinstance(item, dict)}
    return packet, {"artifacts": by_locator, "validators": by_validator}


def _evidence_path(workspace: Path, locator: object) -> Path:
    scope, relative = _split_locator(locator)
    target = workspace / "evidence" / scope / relative
    if not _inside(workspace, target):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    return target


def enforce_reviewer_write_scope(locator: object) -> None:
    text = str(locator or "")
    if text.startswith("source:"):
        raise ReviewerWorkspaceError("WB_REVIEW_SOURCE_WRITE_DENIED", {"classification": "denied"})
    if text.startswith("control:"):
        raise ReviewerWorkspaceError("WB_REVIEW_CONTROL_WRITE_DENIED", {"classification": "denied"})
    raise ReviewerWorkspaceError("WB_REVIEW_WRITE_DENIED", {"classification": "denied"})


def _runtime_identity(workspace: Path) -> tuple[Path, str, dict[str, object]]:
    workspace = workspace.expanduser().resolve()
    if workspace.parent.name != "reviews":
        raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID")
    runtime_root = workspace.parent.parent
    review_id = _safe_id(workspace.name)
    state_path = runtime_root / ".state" / f"{review_id}.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID") from None
    if not isinstance(state, dict) or state.get("review_id") != review_id or state.get("owner") != "work-bundle":
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID")
    return runtime_root, review_id, state


def _append_denial_event(workspace: Path, error: ReviewerWorkspaceError, operation: object) -> None:
    runtime_root, review_id, state = _runtime_identity(workspace)
    events_path = (runtime_root / "events" / f"{review_id}.jsonl").resolve(strict=False)
    if not _inside(runtime_root, events_path):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    events_path.parent.mkdir(parents=True, exist_ok=True)
    if events_path.exists():
        events_path.chmod(0o600)
    operation_name = str(operation or "unknown")
    if operation_name not in {"read", "write", "search", "validate", "network"}:
        operation_name = "unknown"
    event = {
        "schema": "reviewer-denial-event-v1",
        "event_id": f"review-denial-{uuid.uuid4()}",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "review_id": review_id,
        "packet_sha256": state.get("packet_sha256"),
        "event_type": "reviewer_operation_denied",
        "denial_code": error.code,
        "operation": operation_name,
        "privacy": "operational_metadata_only",
    }
    descriptor = os.open(events_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    finally:
        os.close(descriptor)
    events_path.chmod(0o400)


def _seal_event_log(runtime_root: Path, review_id: str) -> dict[str, object]:
    events_path = (runtime_root / "events" / f"{review_id}.jsonl").resolve(strict=False)
    if not _inside(runtime_root, events_path):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    events_path.parent.mkdir(parents=True, exist_ok=True)
    if not events_path.exists():
        descriptor = os.open(events_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        os.close(descriptor)
    events_path.chmod(0o400)
    return {
        "event_log_path": str(events_path),
        "event_log_sha256": _sha256_bytes(events_path.read_bytes()),
        "event_log_mode": "0400",
    }


def _sandbox_denied(completed: subprocess.CompletedProcess[str]) -> bool:
    if completed.returncode == 0:
        return False
    detail = f"{completed.stdout}\n{completed.stderr}".lower()
    return (
        completed.returncode < 0
        or "operation not permitted" in detail
        or "sandbox violation" in detail
        or "permissionerror" in detail
    )


def _run_sandboxed_process(workspace: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    workspace = workspace.expanduser().resolve()
    _, _, state = _runtime_identity(workspace)
    if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise ReviewerWorkspaceError("WB_REVIEW_SANDBOX_UNAVAILABLE", {"classification": "denied"})
    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID", {"classification": "denied"})
    executable = Path(argv[0]).expanduser()
    if not executable.is_absolute() or not executable.is_file():
        raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID", {"classification": "denied"})
    allowed_runtime_roots = [
        Path("/System"),
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        *_runtime_read_roots(),
    ]
    if not any(_inside(root, executable) for root in allowed_runtime_roots):
        raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID", {"classification": "denied"})
    profile = workspace / "sandbox.sb"
    sandbox_state = state.get("sandbox") if isinstance(state.get("sandbox"), dict) else {}
    if not profile.is_file() or profile.is_symlink() or _sha256_bytes(profile.read_bytes()) != sandbox_state.get("profile_sha256"):
        raise ReviewerWorkspaceError("WB_REVIEW_SANDBOX_PROFILE_INVALID", {"classification": "denied"})
    scratch = workspace / "scratch"
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(scratch / "home"),
        "TMPDIR": str(scratch / "tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    (scratch / "home").mkdir(parents=True, exist_ok=True)
    (scratch / "tmp").mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        ["/usr/bin/sandbox-exec", "-f", str(profile), *argv],
        cwd=workspace,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def run_sandboxed_validator(workspace: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one frozen validator argv inside the macOS process sandbox."""
    return _run_sandboxed_process(workspace, argv)


def _task_product_judgment_review(
    judgment: object,
    *,
    review_id: str,
    context: dict[str, object],
    packet: dict[str, object],
    started_at: str,
    completed_at: str,
    previous_review: object = None,
    integrated_stage: bool = False,
) -> dict[str, object]:
    """Compose controller-owned review authority around a compact product judgment."""
    if not isinstance(judgment, dict) or set(judgment) != {"task_review"}:
        raise ReviewerWorkspaceError("WB_REVIEW_TASK_OUTPUT_INVALID")
    product = judgment["task_review"]
    if not isinstance(product, dict) or set(product) != {"reviewed_head", "verdict", "findings"}:
        raise ReviewerWorkspaceError("WB_REVIEW_TASK_OUTPUT_INVALID")
    identity = context["target_identity"]
    if (
        not isinstance(identity, dict)
        or product["reviewed_head"] != (
            identity.get("source_tree") if integrated_stage else identity.get("revision")
        )
        or product["verdict"] not in {"accept", "repair"}
        or not isinstance(product["findings"], list)
    ):
        raise ReviewerWorkspaceError("WB_REVIEW_TASK_OUTPUT_INVALID")
    if product["verdict"] == "repair" and not product["findings"]:
        raise ReviewerWorkspaceError("WB_REVIEW_TASK_OUTPUT_INVALID")
    findings = []
    for item in product["findings"]:
        expected = {"finding_id", "severity", "requirement_id", "boundary", "evidence", "expected", "observed", "owner"}
        if (
            not isinstance(item, dict) or set(item) != expected
            or item["severity"] not in {"blocking", "advisory"}
            or item["owner"] != "task_owner"
            or not all(isinstance(item[key], str) and item[key].strip() for key in expected - {"severity"})
        ):
            raise ReviewerWorkspaceError("WB_REVIEW_TASK_OUTPUT_INVALID")
        advisory = item["severity"] == "advisory"
        findings.append({
            "finding_id": item["finding_id"], "stage": "implementation",
            "class": "advisory_enhancement" if advisory else "implementation_defect",
            "severity": item["severity"], "first_broken_artifact": "implementation",
            "obligation_basis": "none" if advisory else "accepted_requirement",
            "evidence": [{
                "kind": "source", "locator": item["boundary"],
                "digest_or_identity": _canonical_digest({
                    "requirement_id": item["requirement_id"], "evidence": item["evidence"]
                }),
                "observation": f"{item['evidence']} Expected: {item['expected']} Observed: {item['observed']}",
            }],
            "target_identity": identity,
            "summary": f"{item['requirement_id']}: {item['observed']}",
            "recommended_owner": "backlog_owner" if advisory else "task_owner",
            "disposition": "record_advisory" if advisory else "repair_task",
        })
    artifacts = [
        {"path": item["locator"], "sha256": item["sha256"]}
        for item in packet.get("artifacts", []) if isinstance(item, dict)
    ]
    result = {
        "required": True, "reviewer_independent": True, "review_id": review_id,
        "reviewed_head": identity["revision"], "review_mode": context.get("review_mode", "initial"),
        "review_target_kind": "task", "repair_frontier": context.get("repair_frontier"),
        "review_reset": context.get("review_reset"), "target_identity": identity,
        "reviewer": {
            "agent_id": context["agent_id"], "capability": context["capability"],
            "authorship": "none", "repair_participation": "none",
            "decision_participation": "none", "deliberation_participation": "none",
            "context_origin": context["evidence_mode"],
        },
        "evidence": {
            "mode": context["evidence_mode"], "capabilities": ["product review judgment"],
            "unavailable_evidence": [], "commands": [], "artifacts": artifacts,
        },
        "verdict": product["verdict"], "findings": findings,
        "started_at": started_at, "completed_at": completed_at,
        "staleness": {"is_stale": False, "reason": None, "supersedes": None},
    }
    if context.get("review_mode", "initial") == "repair" or context.get("review_reset") is not None:
        if not isinstance(previous_review, dict):
            raise ReviewerWorkspaceError("WB_REVIEW_TASK_CONTROL_INPUT_INVALID")
        result["previous_review"] = previous_review
    if integrated_stage:
        result.pop("required")
        result.pop("reviewer_independent")
        result.pop("reviewed_head")
        result["stage"] = "integrated_implementation"
        result["review_target_kind"] = "stage"
        result["verdict"] = "accepted" if product["verdict"] == "accept" else "repair"
    return result


def _stage_product_judgment_review(
    judgment, *, review_id, context, packet, started_at, completed_at,
    previous_review=None,
):
    """Compose native stage authority without asking the reviewer to invent it."""
    if not isinstance(judgment, dict) or set(judgment) != {"stage_review"}:
        raise ReviewerWorkspaceError("WB_REVIEW_STAGE_OUTPUT_INVALID")
    product = judgment["stage_review"]
    if (not isinstance(product, dict) or set(product) != {"target_identity", "verdict", "findings"}
            or product["target_identity"] != context["target_identity"]
            or product["verdict"] not in TERMINAL_VERDICTS or not isinstance(product["findings"], list)):
        raise ReviewerWorkspaceError("WB_REVIEW_STAGE_OUTPUT_INVALID")
    result = {
        "review_id": review_id, "stage": context["stage"], "target_identity": context["target_identity"],
        "review_mode": context.get("review_mode", "initial"), "review_target_kind": "stage",
        "repair_frontier": context.get("repair_frontier"), "review_reset": context.get("review_reset"),
        "reviewer": {"agent_id": context["agent_id"], "capability": context["capability"],
                     "authorship": "none", "repair_participation": "none", "decision_participation": "none",
                     "deliberation_participation": "none", "context_origin": context["evidence_mode"]},
        "evidence": {"mode": context["evidence_mode"], "capabilities": ["product review judgment"],
                     "unavailable_evidence": [], "commands": [],
                     "artifacts": [{"path": item["locator"], "sha256": item["sha256"]} for item in packet["artifacts"]]},
        "verdict": product["verdict"], "findings": product["findings"],
        "started_at": started_at, "completed_at": completed_at,
        "staleness": {"is_stale": False, "reason": None, "supersedes": None},
    }
    if context.get("review_mode", "initial") == "repair" or context.get("review_reset") is not None:
        if not isinstance(previous_review, dict):
            raise ReviewerWorkspaceError("WB_REVIEW_STAGE_CONTROL_INPUT_INVALID")
        result["previous_review"] = previous_review
    return result


def run_sandboxed_reviewer(workspace: Path, argv: list[str]) -> dict[str, object]:
    """Launch the entire reviewer under the frozen deny-default profile."""
    return _run_reviewer(workspace, argv)


def _run_reviewer(
    workspace: Path,
    argv: list[str],
    *,
    native_request: dict[str, object] | None = None,
    native_controller_evidence: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    workspace = workspace.expanduser().resolve()
    runtime_root, review_id, state = _runtime_identity(workspace)
    packet, _ = _load_workspace(workspace)
    if _canonical_digest(packet) != state.get("packet_sha256") or _artifact_digest(workspace, packet) != state.get("evidence_digest"):
        raise ReviewerWorkspaceError("WB_REVIEW_EVIDENCE_MUTATED")
    if "stage_review_context" in packet:
        try:
            _review_runtime().validate_stage_evidence(
                workspace / "evidence/control",
                _validate_stage_context(packet["stage_review_context"]),
                packet,
            )
        except (ValueError, OSError, SystemExit) as error:
            raise ReviewerWorkspaceError("WB_REVIEW_STAGE_EVIDENCE_INCOMPLETE") from error
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = f"reviewer-run-{uuid.uuid4()}"
    native = native_request is not None
    request_bytes = json.dumps(native_request, sort_keys=True, ensure_ascii=False).encode() if native else b""
    executable_digest = _sha256_bytes(Path(argv[0]).read_bytes()) if native else None
    completed = (_run_native_process(workspace, argv, request_bytes.decode()) if native
                 else _run_sandboxed_process(workspace, argv))
    host_run_id = None
    native_worker_output = None
    if native:
        diagnostic_path = _retain_native_diagnostics(
            runtime_root, run_id, review_id, argv, request_bytes, executable_digest, completed)
        if completed.returncode != 0:
            raise ReviewerWorkspaceError("WB_REVIEW_NATIVE_PROCESS_FAILED", {
                "exit_code": completed.returncode, "diagnostic_path": diagnostic_path})
        if _sha256_bytes(Path(argv[0]).read_bytes()) != executable_digest:
            raise ReviewerWorkspaceError("WB_REVIEW_NATIVE_EXECUTABLE_MUTATED", {"diagnostic_path": diagnostic_path})
        try:
            host_run_id, native_worker_output = parse_native_reviewer_transcript(completed.stdout, completed.stderr)
        except ReviewerWorkspaceError as error:
            raise ReviewerWorkspaceError(error.code, {**error.result, "diagnostic_path": diagnostic_path}) from error
    if _artifact_digest(workspace, packet) != state.get("evidence_digest"):
        raise ReviewerWorkspaceError("WB_REVIEW_EVIDENCE_MUTATED")
    denied = not native and _sandbox_denied(completed)
    if denied:
        _append_denial_event(
            workspace,
            ReviewerWorkspaceError("WB_REVIEW_SANDBOX_DENIED", {"classification": "denied"}),
            "validate",
        )
    sealed = _seal_event_log(runtime_root, review_id)
    sandbox_state = state.get("sandbox") if isinstance(state.get("sandbox"), dict) else {}
    receipt = {
        "schema": "reviewer-native-receipt-v1" if native else "reviewer-process-receipt-v1",
        "run_id": run_id,
        "review_id": review_id,
        "status": "denied" if denied else ("passed" if completed.returncode == 0 else "failed"),
        "packet_sha256": state.get("packet_sha256"),
        "sandbox_profile_sha256": sandbox_state.get("profile_sha256"),
        "argv_sha256": _canonical_digest(argv),
        "exit_code": completed.returncode,
        "stdout_sha256": _sha256_bytes(completed.stdout.encode("utf-8")),
        "stderr_sha256": _sha256_bytes(completed.stderr.encode("utf-8")),
        "event_log_sha256": sealed["event_log_sha256"],
        "event_log_mode": sealed["event_log_mode"],
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if native:
        receipt.update({"host_run_id": host_run_id, "request_sha256": _sha256_bytes(request_bytes),
                        "executable_sha256": executable_digest, "isolation": dict(NATIVE_ISOLATION)})
    context_key = "stage_review_context" if "stage_review_context" in packet else (
        "task_review_context" if "task_review_context" in packet else None
    )
    if context_key is not None:
        context = (
            _validate_stage_context(packet[context_key])
            if context_key == "stage_review_context"
            else _validate_task_context(packet[context_key])
        )
        try:
            worker_output = native_worker_output if native else json.loads(completed.stdout)
            if native:
                context = {**context, "agent_id": host_run_id, "execution_id": host_run_id}
            compact_integrated = (
                context_key == "stage_review_context"
                and context.get("stage") == "integrated_implementation"
                and isinstance(worker_output, dict) and "task_review" in worker_output
            )
            review = (
                _task_product_judgment_review(
                    worker_output, review_id=review_id, context=context, packet=packet,
                    started_at=started_at, completed_at=receipt["completed_at"],
                    previous_review=state.get(
                        "task_review_previous_review"
                        if context_key == "task_review_context"
                        else "stage_review_previous_review"
                    ),
                    integrated_stage=compact_integrated,
                )
                if context_key == "task_review_context" or compact_integrated
                else (_stage_product_judgment_review(
                    worker_output, review_id=review_id, context=context, packet=packet,
                    started_at=started_at, completed_at=receipt["completed_at"],
                    previous_review=state.get("stage_review_previous_review"))
                    if native else worker_output)
            )
            validated = (
                _review_runtime()._validated_review_envelope(review)
                if context_key == "stage_review_context"
                else _review_runtime().validate_task_acceptance_review(review)
            )
        except (ValueError, TypeError) as error:
            code = "WB_REVIEW_TASK_OUTPUT_INVALID" if context_key == "task_review_context" else "WB_REVIEW_STAGE_OUTPUT_INVALID"
            raise ReviewerWorkspaceError(code) from error
        mode = "direct_source" if validated.evidence["mode"] == "direct" else validated.evidence["mode"]
        review_context = {
            "review_mode": review.get("review_mode", "initial"),
            "review_target_kind": review.get("review_target_kind", "stage"),
            "repair_frontier": review.get("repair_frontier"),
            "review_reset": review.get("review_reset"),
        }
        packet_context = {
            "review_mode": context.get("review_mode", "initial"),
            "review_target_kind": context.get("review_target_kind", "stage"),
            "repair_frontier": context.get("repair_frontier"),
            "review_reset": context.get("review_reset"),
        }
        if ("reviewer_run" in review or validated.review_id != review_id
                or (context_key == "stage_review_context" and validated.stage != context["stage"])
                or validated.target_identity != context["target_identity"]
                or validated.reviewer["agent_id"] != context["agent_id"]
                or validated.reviewer["context_origin"] != context["evidence_mode"]
                or validated.reviewer["capability"] != context["capability"] or mode != context["evidence_mode"]
                or review_context != packet_context):
            raise ReviewerWorkspaceError("WB_REVIEW_STAGE_OUTPUT_MISMATCH")
        if validated.verdict == "accepted" and context_key == "stage_review_context":
            try:
                _review_runtime().validate_stage_evidence(workspace / "evidence/control", context, packet)
            except (ValueError, OSError, SystemExit) as error:
                raise ReviewerWorkspaceError("WB_REVIEW_STAGE_EVIDENCE_INCOMPLETE") from error
        receipt[context_key] = context
        receipt["review_result_sha256"] = _canonical_digest(review)
        if native or context_key == "task_review_context" or compact_integrated:
            receipt["review_result"] = review
        if not native:
            receipt["isolation"] = {"mechanism": "sandbox-exec", "network": "denied", "write_scope": "scratch"}
    receipt_path = (runtime_root / "receipts" / "reviewer-process" / f"{run_id}.json").resolve(strict=False)
    if not _inside(runtime_root, receipt_path):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    # Retain immutable run-scoped evidence after workspace cleanup or later runs.
    retained_items = [("packet.json", json.dumps(packet, sort_keys=True).encode()),
                      ("events.jsonl", Path(str(sealed["event_log_path"])).read_bytes())]
    if native:
        retained_items.extend([("request.json", request_bytes), ("stdout.jsonl", completed.stdout.encode()),
                               ("stderr.txt", completed.stderr.encode()),
                               ("launch.json", json.dumps({"argv": argv, "executable_sha256": executable_digest}, sort_keys=True).encode())])
        if native_controller_evidence is not None:
            retained_items.append(
                (
                    "controller.json",
                    json.dumps(native_controller_evidence, sort_keys=True, ensure_ascii=False).encode(),
                )
            )
    else:
        retained_items.append(("profile.sb", (workspace / "sandbox.sb").read_bytes()))
    for suffix, content in retained_items:
        retained = receipt_path.with_suffix(f".{suffix}")
        with retained.open("xb") as stream:
            stream.write(content)
        retained.chmod(0o400)
    with receipt_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    receipt_path.chmod(0o400)
    reference = {"run_id": run_id, "sha256": _sha256_bytes(receipt_path.read_bytes())}
    return {**receipt, "receipt_path": str(receipt_path), "event_log_path": sealed["event_log_path"],
            **({"reviewer_run": reference} if context_key is not None else {})}


def _execute_reviewer_request(workspace: Path, request: dict[str, object]) -> dict[str, object]:
    workspace = workspace.expanduser().resolve()
    packet, indexes = _load_workspace(workspace)
    operation = str(request.get("operation") or "")
    if operation == "write":
        enforce_reviewer_write_scope(request.get("artifact"))
    if operation == "network":
        raise ReviewerWorkspaceError("WB_REVIEW_NETWORK_DENIED", {"classification": "denied"})
    if operation == "read":
        locator = str(request.get("artifact") or "")
        _split_locator(locator)
        record = indexes["artifacts"].get(locator)
        if not isinstance(record, dict):
            raise ReviewerWorkspaceError("WB_REVIEW_PROTECTED_READ_DENIED", {"classification": "denied"})
        target = _evidence_path(workspace, locator)
        if _sha256_bytes(target.read_bytes()) != record.get("sha256"):
            raise ReviewerWorkspaceError("WB_REVIEW_EVIDENCE_MUTATED")
        return {"status": "allowed", "artifact": locator, "content": target.read_text(encoding="utf-8")}
    if operation == "search":
        pattern = str(request.get("pattern") or "")
        if not pattern or len(pattern) > 256 or "\n" in pattern:
            raise ReviewerWorkspaceError("WB_REVIEW_SEARCH_PATTERN_INVALID")
        allowed_roots = packet.get("search_roots")
        if not isinstance(allowed_roots, list):
            raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID")
        matches: list[str] = []
        for locator, record in sorted(indexes["artifacts"].items()):
            if not isinstance(record, dict) or not any(
                locator == root or locator.startswith(f"{root.rstrip('/')}/") for root in allowed_roots
            ):
                continue
            target = _evidence_path(workspace, locator)
            if _sha256_bytes(target.read_bytes()) != record.get("sha256"):
                raise ReviewerWorkspaceError("WB_REVIEW_EVIDENCE_MUTATED")
            for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
                if pattern in line:
                    matches.append(f"{locator}:{number}:{line.strip()}")
        return {"status": "allowed", "matches": matches}
    if operation == "validate":
        validator_id = str(request.get("validator_id") or "")
        validator = indexes["validators"].get(validator_id)
        if not isinstance(validator, dict):
            raise ReviewerWorkspaceError("WB_REVIEW_VALIDATOR_DENIED", {"classification": "denied"})
        if validator.get("kind") == "command":
            argv = validator.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
                raise ReviewerWorkspaceError("WB_REVIEW_VALIDATOR_DENIED", {"classification": "denied"})
            completed = run_sandboxed_validator(workspace, argv)
            if completed.returncode:
                if _sandbox_denied(completed):
                    raise ReviewerWorkspaceError(
                        "WB_REVIEW_SANDBOX_DENIED",
                        {"classification": "denied", "validator_id": validator_id, "exit_code": completed.returncode},
                    )
                return {
                    "status": "allowed",
                    "validator_id": validator_id,
                    "result": "failed",
                    "exit_code": completed.returncode,
                    "stdout_sha256": _sha256_bytes(completed.stdout.encode("utf-8")),
                    "stderr_sha256": _sha256_bytes(completed.stderr.encode("utf-8")),
                }
            return {
                "status": "allowed",
                "validator_id": validator_id,
                "result": "passed",
                "exit_code": 0,
                "stdout_sha256": _sha256_bytes(completed.stdout.encode("utf-8")),
                "stderr_sha256": _sha256_bytes(completed.stderr.encode("utf-8")),
            }
        locator = str(validator.get("artifact") or "")
        record = indexes["artifacts"].get(locator)
        target = _evidence_path(workspace, locator)
        if not isinstance(record, dict) or _sha256_bytes(target.read_bytes()) != record.get("sha256"):
            raise ReviewerWorkspaceError("WB_REVIEW_EVIDENCE_MUTATED")
        if validator.get("kind") == "json":
            try:
                json.loads(target.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"status": "allowed", "validator_id": validator_id, "result": "failed"}
            result = "passed"
        elif validator.get("kind") == "sha256":
            result = str(record["sha256"])
        else:
            raise ReviewerWorkspaceError("WB_REVIEW_VALIDATOR_DENIED", {"classification": "denied"})
        return {"status": "allowed", "validator_id": validator_id, "result": result}
    raise ReviewerWorkspaceError("WB_REVIEW_OPERATION_DENIED", {"classification": "denied"})


def execute_reviewer_request(workspace: Path, request: dict[str, object]) -> dict[str, object]:
    try:
        return _execute_reviewer_request(workspace, request)
    except ReviewerWorkspaceError as error:
        _append_denial_event(workspace, error, request.get("operation"))
        raise


def cleanup_reviewer_workspace(
    runtime_root: Path,
    review_id: str,
    *,
    terminal_review: dict[str, object] | None = None,
    source_root: Path | None = None,
    control_root: Path | None = None,
    protected_roots: list[Path] | None = None,
    terminal_evidence: str | None = None,
) -> dict[str, object]:
    workspace, state_path = _workspace_paths(runtime_root, review_id)
    if terminal_evidence is not None or not isinstance(terminal_review, dict):
        raise ReviewerWorkspaceError("WB_REVIEW_TERMINAL_RECORD_INVALID")
    if not state_path.is_file() or state_path.is_symlink():
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_MISSING")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID") from None
    if (
        not isinstance(state, dict)
        or state.get("owner") != "work-bundle"
        or state.get("review_id") != review_id
        or state.get("workspace_token") != f"reviews/{review_id}"
        or not workspace.is_dir()
        or workspace.is_symlink()
    ):
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID")
    required_terminal = {"schema", "review_id", "packet_sha256", "verdict", "evidence_digest", "sentinel_digest"}
    if (
        set(terminal_review) != required_terminal
        or terminal_review.get("schema") != "reviewer-terminal-review-v1"
        or terminal_review.get("review_id") != review_id
        or terminal_review.get("packet_sha256") != state.get("packet_sha256")
        or terminal_review.get("verdict") not in TERMINAL_VERDICTS
    ):
        raise ReviewerWorkspaceError("WB_REVIEW_TERMINAL_RECORD_INVALID")
    packet_path = workspace / "packet.json"
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID") from None
    if _canonical_digest(packet) != state.get("packet_sha256"):
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID")
    evidence_digest = _artifact_digest(workspace, packet)
    if source_root is None or control_root is None:
        raise ReviewerWorkspaceError("WB_REVIEW_TERMINAL_RECORD_INVALID")
    protected = _normalized_roots(protected_roots or [])
    supplied_root_identities = _root_identity_digests(
        source_root.expanduser().resolve(), control_root.expanduser().resolve(), protected
    )
    if supplied_root_identities != state.get("root_identity_digests"):
        raise ReviewerWorkspaceError("WB_REVIEW_ROOT_IDENTITY_MISMATCH")
    sentinel_digest = _sentinel_digest(
        source_root.expanduser().resolve(),
        control_root.expanduser().resolve(),
        protected,
        list(packet.get("sentinels", [])),
    )
    if (
        evidence_digest != state.get("evidence_digest")
        or sentinel_digest != state.get("sentinel_digest")
        or terminal_review.get("evidence_digest") != evidence_digest
        or terminal_review.get("sentinel_digest") != sentinel_digest
    ):
        raise ReviewerWorkspaceError("WB_REVIEW_TERMINAL_EVIDENCE_CHANGED")
    terminal_record_digest = _canonical_digest(terminal_review)
    receipt = {
        "schema": "reviewer-workspace-cleanup-v1",
        "review_id": review_id,
        "owner": "work-bundle",
        "packet_sha256": state["packet_sha256"],
        "terminal_review_sha256": terminal_record_digest,
        "evidence_digest": evidence_digest,
        "sentinel_digest": sentinel_digest,
        "status": "cleaned",
    }
    resolved_runtime = runtime_root.expanduser().resolve()
    receipt_path = (resolved_runtime / "receipts" / f"{review_id}.json").resolve(strict=False)
    if not _inside(resolved_runtime, receipt_path):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    pending = {**receipt, "status": "cleanup-pending"}
    receipt_path.write_text(json.dumps(pending, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.rmtree(workspace)
    state_path.unlink()
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "receipt_path": str(receipt_path)}


def cmd_reviewer_workspace(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"wb.py {command}")
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--review-id", required=True)
    if command == "reviewer-workspace-create":
        parser.add_argument("--packet", required=True)
    elif command == "reviewer-process-run":
        parser.add_argument("--argv-json", required=True)
    elif command == "reviewer-workspace-operation":
        parser.add_argument("--request", required=True)
    elif command == "reviewer-workspace-cleanup":
        parser.add_argument("--terminal-review", required=True)
        parser.add_argument("--source-root", required=True)
        parser.add_argument("--control-root", required=True)
        parser.add_argument("--protected-root", action="append", required=True)
    else:
        raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID")
    args = parser.parse_args(argv)
    runtime_root = Path(args.runtime_root)
    if command == "reviewer-workspace-create":
        result = create_reviewer_workspace(runtime_root, args.review_id, json.loads(Path(args.packet).read_text(encoding="utf-8")))
    elif command == "reviewer-process-run":
        argv_value = json.loads(Path(args.argv_json).read_text(encoding="utf-8"))
        if not isinstance(argv_value, list):
            raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID")
        workspace, _ = _workspace_paths(runtime_root, args.review_id)
        result = run_sandboxed_reviewer(workspace, argv_value)
    elif command == "reviewer-workspace-operation":
        workspace, _ = _workspace_paths(runtime_root, args.review_id)
        result = execute_reviewer_request(workspace, json.loads(Path(args.request).read_text(encoding="utf-8")))
    else:
        result = cleanup_reviewer_workspace(
            runtime_root,
            args.review_id,
            terminal_review=json.loads(Path(args.terminal_review).read_text(encoding="utf-8")),
            source_root=Path(args.source_root),
            control_root=Path(args.control_root),
            protected_roots=[Path(value) for value in args.protected_root],
        )
    print(json.dumps(result, sort_keys=True))
    return 0
