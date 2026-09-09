#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from artifact_inputs import _as_list, _input_path, _read_structured, _resolve_spec_paths, parse_yaml_subset


ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")

FINDING_STAGES = frozenset({"specification", "plan", "implementation", "validation", "environment"})
FINDING_SEVERITIES = frozenset({"blocking", "non_blocking", "advisory"})
OBLIGATION_BASES = frozenset({"accepted_requirement", "essential_safety", "evidence_integrity", "none"})
TERMINAL_FINDING_DISPOSITIONS = frozenset({"accepted", "rejected"})
STAGE_REVIEW_STAGES = frozenset({"specification", "plan", "integrated_implementation"})
REVIEW_VERDICTS = frozenset({"accepted", "repair", "blocked"})
REVIEW_MODES = frozenset({"initial", "repair"})
REVIEW_TARGET_KINDS = frozenset({"task", "stage"})
MATERIAL_CHANGE_CLASSES = frozenset(
    {"material_redesign", "authority", "scope", "acceptance", "decomposition", "validation_allocation"}
)
EVIDENCE_CAUSAL_CLASSES = frozenset(
    {
        "claim_relevant_drift",
        "implementation_defect",
        "authority_plan_gap",
        "evaluator_control_defect",
        "non_claim_relevant",
    }
)
EVIDENCE_CAUSAL_ROUTES: dict[str, tuple[str, str]] = {
    "claim_relevant_drift": ("revalidate_claim", "route_current_owner"),
    "implementation_defect": ("repair_task", "route_current_owner"),
    "authority_plan_gap": ("repair_authority_plan", "route_current_owner"),
    "evaluator_control_defect": ("repair_evaluator_control", "route_evaluator_control_owner"),
    "non_claim_relevant": ("none", "diagnostic_only"),
}
EVIDENCE_CAUSAL_COMPARISONS = {
    "claim_relevant_drift": "claim_relevant",
    "implementation_defect": "claim_relevant",
    "authority_plan_gap": "claim_relevant",
    "evaluator_control_defect": "evaluator_only",
    "non_claim_relevant": "unrelated",
}
PARTICIPATION_FIELDS = (
    "authorship",
    "repair_participation",
    "decision_participation",
    "deliberation_participation",
)

ROUTES: dict[str, tuple[str, str, str]] = {
    "specification_gap": ("specification", "specification_owner", "reopen_specification"),
    "decomposition_gap": ("plan", "plan_owner", "repair_plan"),
    "allocation_gap": ("plan", "plan_owner", "reslice_plan"),
    "implementation_defect": ("implementation", "task_owner", "repair_task"),
    "validation_oracle_defect": ("validation_oracle", "oracle_owner", "repair_oracle"),
    "environment_failure": ("environment", "environment_owner", "recover_environment"),
    "advisory_enhancement": ("implementation", "backlog_owner", "record_advisory"),
}

FINDING_KEYS = frozenset(
    {
        "finding_id",
        "stage",
        "class",
        "severity",
        "first_broken_artifact",
        "obligation_basis",
        "evidence",
        "target_identity",
        "summary",
        "recommended_owner",
        "disposition",
    }
)
TARGET_KEYS = frozenset({"artifact_id", "revision", "sha256", "source_tree"})
AFFECTED_REGION_KEYS = frozenset({"task_ids", "paths", "interfaces", "validation_oracles"})
BINDING_IDENTITY_KEYS = frozenset({"binding_id", "sha256"})
BASELINE_IDENTITY_KEYS = frozenset({"head", "tree"})
PLAN_RETURN_KEYS = frozenset(
    {
        "finding_id",
        "first_broken_artifact",
        "return_to",
        "action",
        "execution_state",
        "affected_region",
        "returned_authority_identity",
        "preserved_evidence_identities",
        "resume_requires",
        "original_binding_identity",
        "original_baseline_identity",
        "preserve_valid_work_and_evidence",
        "silent_expansion_allowed",
    }
)
EVIDENCE_ITEM_KEYS = frozenset({"kind", "locator", "digest_or_identity", "observation"})
EVIDENCE_CAUSAL_CLASSIFICATION_KEYS = frozenset(
    {
        "observation_reference",
        "accepted_authority_comparison",
        "causal_class",
        "affected_claim",
        "affected_owner",
        "authorized_lifecycle_action",
        "disposition",
    }
)
ACCEPTED_AUTHORITY_COMPARISON_KEYS = frozenset({"authority_identity", "result", "basis"})
STAGE_REVIEW_KEYS = frozenset(
    {"review_id", "review_mode", "review_target_kind", "repair_frontier", "review_reset", "stage", "target_identity", "reviewer", "evidence", "verdict", "findings", "started_at", "completed_at", "staleness"}
)
LEGACY_STAGE_REVIEW_KEYS = STAGE_REVIEW_KEYS - {"review_mode", "review_target_kind", "repair_frontier", "review_reset"}
REPAIR_FRONTIER_KEYS = frozenset(
    {"prior_review_id", "blocking_finding_ids", "previous_reviewed_identity", "repaired_identity", "affected_boundaries", "frozen_evidence_reference"}
)
REVIEW_RESET_KEYS = frozenset({"prior_review_id", "reason_class", "reason"})
REVIEWER_KEYS = frozenset(
    {"agent_id", "capability", *PARTICIPATION_FIELDS, "context_origin"}
)
REVIEW_EVIDENCE_KEYS = frozenset({"mode", "capabilities", "unavailable_evidence", "commands", "artifacts"})
COMMAND_KEYS = frozenset({"command_id", "purpose", "exit_code", "output_digest"})
ARTIFACT_KEYS = frozenset({"path", "sha256"})
STALENESS_KEYS = frozenset({"is_stale", "reason", "supersedes"})


class ReviewContractError(ValueError):
    pass


def reviewer_runtime_root(root: Path) -> Path:
    """Controller-owned runtime location; never selected by a review envelope."""
    workspace_key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()
    return Path.home() / ".work-bundle/reviewer-runtime/workspaces" / workspace_key


def stage_target_identity(root: Path, stage: str, path: Path, *, source_root: Path | None = None) -> dict[str, Any]:
    identity = artifact_review_identity(path) if stage == "specification" else plan_review_identity(root, path)
    if stage == "integrated_implementation":
        if source_root is None:
            raise ReviewContractError("review provenance requires source repository")
        result = subprocess.run(["git", "-C", str(source_root), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True)
        tree = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD^{tree}"], capture_output=True, text=True)
        if result.returncode or result.stdout.strip() or tree.returncode:
            raise ReviewContractError("review provenance requires clean source tree")
        identity["source_tree"] = tree.stdout.strip()
    return identity


_ACCEPTED_RESULT_FIELDS = {
    "schema", "plan_id", "task_id", "binding_id", "baseline_identity",
    "accepted_source", "authority_projection", "executor_result_digest",
    "validation_evidence_ids", "review_id", "owner_identity", "accepted_at",
    "invalidation",
}
_ACCEPTED_AUTHORITY_FIELDS = {
    "task_digest", "binding_digest", "scope_digest", "validation_obligations_digest",
    "required_review_digest", "ownership_digest",
}


def accepted_result_state_digest(accepted: Mapping[str, Any]) -> str:
    """Recompute the compact accepted-result identity without importing execution runtime."""

    source = _mapping(accepted.get("accepted_source"), "accepted task result source")
    state = {
        "plan_id": accepted.get("plan_id"), "task_id": accepted.get("task_id"),
        "binding_id": accepted.get("binding_id"),
        "baseline_identity": dict(_mapping(accepted.get("baseline_identity"), "accepted baseline")),
        "accepted_source": {"head": source.get("head"), "tree": source.get("tree")},
        "authority_projection": dict(_mapping(accepted.get("authority_projection"), "accepted authority")),
    }
    if "knowledge_disposition" in accepted:
        state["knowledge_disposition"] = dict(
            _mapping(accepted.get("knowledge_disposition"), "accepted knowledge disposition")
        )
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _accepted_task_stage_evidence(
    root: Path,
    plan_id: str,
    task_id: str,
    task_path: Path,
    *,
    validate_native_receipt: bool,
) -> tuple[Path | None, Path | None, str | None]:
    binding = root / ".work-bundle/runtime/execution" / plan_id / task_id / "execution-binding.json"
    if binding.is_symlink() or not binding.is_file() or not binding.resolve().is_relative_to(root.resolve()):
        return None, None, f"accepted_task_result_missing:{task_id}"
    try:
        from execution_context import assert_accepted_task_result_current, compile_task_authority

        payload = _mapping(json.loads(binding.read_text()), "task execution binding")
        accepted = _mapping(payload.get("accepted_result"), "accepted task result")
        fields = set(accepted)
        if frozenset(fields) not in {
            frozenset(_ACCEPTED_RESULT_FIELDS),
            frozenset(_ACCEPTED_RESULT_FIELDS | {"knowledge_disposition"}),
        }:
            raise ReviewContractError("accepted task result shape is not closed")
        source = _mapping(accepted.get("accepted_source"), "accepted task result source")
        authority = _mapping(accepted.get("authority_projection"), "accepted task result authority")
        ownership = _mapping(payload.get("ownership"), "task execution ownership")
        observations = accepted.get("validation_evidence_ids")
        if (
            accepted.get("schema") != "accepted-task-result-v1"
            or accepted.get("plan_id") != plan_id or accepted.get("task_id") != task_id
            or accepted.get("binding_id") != ownership.get("binding_id")
            or payload.get("plan_id") != plan_id or payload.get("task_id") != task_id
            or accepted.get("invalidation") is not None
            or set(source) != {"head", "tree", "state_digest"}
            or set(authority) != _ACCEPTED_AUTHORITY_FIELDS
            or not isinstance(observations, list) or not observations
            or any(not isinstance(item, str) or not item for item in observations)
            or len(observations) != len(set(observations))
            or source.get("state_digest") != accepted_result_state_digest(accepted)
        ):
            raise ReviewContractError("accepted task result binding or evidence is invalid")
        if validate_native_receipt:
            try:
                current_task = compile_task_authority(root, task_path)
            except SystemExit as error:
                raise ReviewContractError(str(error)) from error
            try:
                assert_accepted_task_result_current(current_task, payload, accepted)
            except SystemExit as error:
                raise ReviewContractError(str(error)) from error
        review_path = None
        if accepted.get("review_id"):
            review_path = _review_store_path(root, str(accepted["review_id"]))
            if review_path.exists():
                if review_path.is_symlink() or review_path.stat().st_mode & 0o222:
                    raise ReviewContractError("stored current task review is mutable")
                review = _mapping(json.loads(review_path.read_text()), "stored current task review")
                validated = _validated_review_envelope(review)
                if (
                    validated.review_id != accepted["review_id"]
                    or review.get("review_target_kind") != "task"
                    or validated.verdict != "accepted"
                    or validated.target_identity.get("artifact_id") != task_id
                    or validated.target_identity.get("revision") != source.get("head")
                    or validated.target_identity.get("source_tree") != source.get("tree")
                ):
                    raise ReviewContractError("stored current task review does not bind accepted source")
                if validate_native_receipt:
                    _validate_reviewer_run(root, review)
            else:
                # Accepted tasks predating native publication remain authoritative.
                review_path = None
        return binding, review_path, None
    except (OSError, ValueError, TypeError, ReviewContractError):
        return binding, None, f"accepted_task_result_invalid:{task_id}"


def stage_evidence_requirements(
    root: Path, stage: str, target: Path, *, validate_native_receipts: bool = True
) -> tuple[dict[str, str], list[str]]:
    """Derive the stage's evidence closure, not a caller-selected context projection.

    Carried knowledge constraints are authority in the specification itself. Their
    protected origin notes are deliberately not retrieved. Validation acceptance
    remains owned by the existing lifecycle gates; here we require its evidence
    to be available to the reviewer, including the native observation store.
    """
    required: dict[str, str] = {}
    missing: list[str] = []

    def control(path: Path, role: str) -> None:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ReviewContractError("stage evidence path escapes control store")
        required["control:" + path.relative_to(root).as_posix()] = role

    control(target, "target")
    data, _ = _read_structured(target)
    members = [target]
    specifications = [target] if stage == "specification" else []
    if stage != "specification":
        for path in sorted((root / ".work-bundle/orchestration/plan").rglob("*.md")):
            path = _input_path(path, root, root / ".work-bundle/orchestration/plan", "stage plan member")
            item, _ = _read_structured(path)
            if item.get("plan_id") == data.get("id"):
                control(path, "plan_member")
                members.append(path)
        for member in members:
            item, _ = _read_structured(member)
            for spec in _resolve_spec_paths(root, item, data):
                if spec not in specifications:
                    specifications.append(spec)
                control(spec, "verified_specification")
                if _read_structured(spec)[0].get("status") != "verified":
                    missing.append("verified_specification:" + spec.relative_to(root).as_posix())
    for spec in specifications:
        item, _ = _read_structured(spec)
        for authority in _as_list(item.get("source_knowledge")):
            if not isinstance(authority, dict) or not str(authority.get("constraint", "")).strip():
                missing.append("carried_authority:" + spec.relative_to(root).as_posix())
        basis = item.get("truth_basis", {})
        if isinstance(basis, dict):
            for reference in _as_list(basis.get("as_is_evidence")):
                # File locators are explicit inputs, not prose or arbitrary URLs.
                if not isinstance(reference, str):
                    missing.append("unsupported_truth_basis_reference")
                    continue
                locator = reference if reference.startswith(("source:", "control:")) else "source:" + reference
                scope, relative = locator.split(":", 1)
                path = Path(relative)
                if path.is_absolute() or ".." in path.parts or not relative or scope not in {"source", "control"}:
                    missing.append("unsupported_truth_basis_reference")
                elif scope == "control":
                    control(root / path, "truth_basis")
                else:
                    required[locator] = "truth_basis"
    if stage == "integrated_implementation":
        for member in members:
            item, _ = _read_structured(member)
            if not item.get("validation"):
                continue
            task_id = str(item.get("id") or "")
            binding, review, failure = _accepted_task_stage_evidence(
                root, str(data.get("id") or ""), task_id, member,
                validate_native_receipt=validate_native_receipts,
            )
            if failure:
                missing.append(failure)
                continue
            assert binding is not None
            control(binding, "accepted_task_result")
            if review is not None:
                control(review, "accepted_task_review")
        # Preserve native identities/receipts; do not invent a parallel validation store.
        path = root / ".work-bundle/runtime/completion-provenance/completion-provenance-v1.json"
        if path.is_file():
            control(path, "validation_observation")
    return required, sorted(set(missing))


def source_snapshot_entries(source_root: Path) -> list[dict[str, str]]:
    """Exact committed regular-file tree; symlinks/submodules fail closed."""
    result = subprocess.run(["git", "-C", str(source_root), "ls-tree", "-rz", "HEAD"], capture_output=True)
    if result.returncode:
        raise ReviewContractError("stage evidence source tree unavailable")
    entries = []
    for row in result.stdout.split(b"\0"):
        if not row:
            continue
        header, raw_path = row.split(b"\t", 1)
        mode, kind, oid = header.decode().split()
        path = raw_path.decode("utf-8")
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ReviewContractError("stage evidence snapshot requires regular files (no symlinks/submodules)")
        entries.append({"locator": "source:" + path, "git_mode": mode, "git_blob": oid})
    return entries


def snapshot_tree_identity(entries: list[dict[str, str]]) -> str:
    tree: dict[str, Any] = {}
    for entry in entries:
        locator = entry["locator"]
        if not locator.startswith("source:") or entry["git_mode"] not in {"100644", "100755"}:
            raise ReviewContractError("invalid source snapshot entry")
        parts = locator[7:].split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ReviewContractError("invalid source snapshot path")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ReviewContractError("source snapshot path collision")
        if parts[-1] in node:
            raise ReviewContractError("source snapshot duplicate path")
        node[parts[-1]] = (entry["git_mode"], entry["git_blob"])

    def digest(node: dict[str, Any]) -> str:
        rows = []
        for name, value in node.items():
            directory = isinstance(value, dict)
            mode, oid = ("40000", digest(value)) if directory else value
            rows.append((name.encode() + (b"/" if directory else b""), mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(oid)))
        content = b"".join(row for _, row in sorted(rows))
        return hashlib.sha1(b"tree " + str(len(content)).encode() + b"\0" + content).hexdigest()
    return digest(tree)


def stage_evidence_manifest(root: Path, source_root: Path, context: Mapping[str, Any], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    locator = str(context["target_locator"])
    if not locator.startswith("control:"):
        raise ReviewContractError("stage evidence target must be control-local")
    target = root / locator[8:]
    if context.get("review_mode", "initial") == "repair":
        # Repair packets carry the repaired target and a compact immutable
        # reference to prior evidence. Full durable history remains lazy.
        required, missing = {locator: "target"}, []
    else:
        required, missing = stage_evidence_requirements(root, str(context["stage"]), target)
    source = (source_snapshot_entries(source_root)
              if context["stage"] == "integrated_implementation" and context.get("review_mode", "initial") == "initial"
              else [])
    for entry in source:
        required.setdefault(entry["locator"], "source_tree")
    available = {item["locator"]: item for item in artifacts}
    for entry in source:
        path = source_root / entry["locator"][7:]
        content = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if path.is_symlink() or blob != entry["git_blob"]:
            raise ReviewContractError("stage evidence source bytes differ from committed tree")
    entries = []
    for key, role in sorted(required.items()):
        if key not in available:
            missing.append(key)
            continue
        entry = {"locator": key, "role": role, "sha256": available[key]["sha256"]}
        if role in {"target", "plan_member", "verified_specification"}:
            path = root / key[8:]
            entry["identity"] = _stage_authority_identity(
                path, stage=str(context["stage"]), role=role
            )
        entries.append(entry)
    return {"schema": "stage-evidence-manifest-v1", "stage": context["stage"],
            "target_identity": context["target_identity"], "entries": entries,
            "source_tree": source, "missing": sorted(set(missing)),
            **({"repair_frontier_reference": context["repair_frontier"]["frozen_evidence_reference"]}
               if context.get("review_mode") == "repair" else {})}


def _stage_authority_identity(
    path: Path,
    *,
    stage: str,
    role: str,
    content: str | None = None,
) -> dict[str, Any]:
    if stage != "specification" and role in {"target", "plan_member"}:
        identity = artifact_review_identity(path, content=content)
        identity["sha256"] = _semantic_plan_artifact_digest(
            _semantic_plan_artifact(path, content=content)
        )
        return identity
    return artifact_review_identity(path, content=content)


def validate_stage_evidence(
    root: Path,
    context: Mapping[str, Any],
    packet: Mapping[str, Any],
    *,
    frozen_control_evidence: Mapping[str, str] | None = None,
) -> None:
    manifest = packet.get("stage_evidence_manifest")
    if (not isinstance(manifest, dict) or manifest.get("schema") != "stage-evidence-manifest-v1"
            or manifest.get("stage") != context["stage"] or manifest.get("target_identity") != context["target_identity"]
            or manifest.get("missing") != [] or context.get("evidence_mode") != "reproducible_snapshot"):
        raise ReviewContractError("stage evidence requires a complete reproducible snapshot")
    target = str(context["target_locator"])
    if not target.startswith("control:"):
        raise ReviewContractError("stage evidence target must be control-local")
    if context.get("review_mode", "initial") == "repair":
        frontier = _repair_frontier(context.get("repair_frontier"))
        if manifest.get("repair_frontier_reference") != frontier["frozen_evidence_reference"]:
            raise ReviewContractError("repair stage evidence does not bind frozen evidence")
        required, missing = {target: "target"}, []
    else:
        required, missing = stage_evidence_requirements(
            root, str(context["stage"]), root / target[8:], validate_native_receipts=False
        )
    source = manifest.get("source_tree", [])
    if context["stage"] == "integrated_implementation" and context.get("review_mode", "initial") == "initial":
        if snapshot_tree_identity(source) != context["target_identity"]["source_tree"]:
            raise ReviewContractError("stage evidence source snapshot is incomplete")
        for entry in source:
            required.setdefault(entry["locator"], "source_tree")
    elif source:
        raise ReviewContractError("unexpected source snapshot")
    entries = {entry["locator"]: entry for entry in manifest.get("entries", [])}
    artifacts = {entry["locator"]: entry for entry in packet["artifacts"]}
    if missing or set(entries) != set(required) or len(entries) != len(manifest["entries"]):
        raise ReviewContractError("stage evidence closure is incomplete")
    for locator, role in required.items():
        entry = entries[locator]
        if entry.get("role") != role or locator not in artifacts or entry.get("sha256") != artifacts[locator].get("sha256"):
            raise ReviewContractError("stage evidence artifact binding mismatch")
        if role in {"target", "plan_member", "verified_specification"}:
            path = root / locator[8:]
            current_identity = _stage_authority_identity(
                path, stage=str(context["stage"]), role=role
            )
            if entry.get("identity") == current_identity:
                continue
            frozen_content = (frozen_control_evidence or {}).get(locator)
            if frozen_content is None:
                raise ReviewContractError("stage evidence authority identity changed")
            if (
                hashlib.sha256(frozen_content.encode()).hexdigest()
                != artifacts[locator].get("sha256")
            ):
                raise ReviewContractError("stage evidence artifact binding mismatch")
            frozen_raw_identity = artifact_review_identity(path, content=frozen_content)
            frozen_semantic_identity = _stage_authority_identity(
                path,
                stage=str(context["stage"]),
                role=role,
                content=frozen_content,
            )
            if (
                entry.get("identity") != frozen_raw_identity
                or frozen_semantic_identity != current_identity
            ):
                raise ReviewContractError("stage evidence authority identity changed")


def _known_execution_ids(root: Path, stage: str, identity: Mapping[str, Any]) -> set[str]:
    area = root / ".work-bundle/orchestration" / ("spec" if stage == "specification" else "plan")
    ids: set[str] = set()
    for path in area.rglob("*.md"):
        if not path.resolve().is_relative_to(area.resolve()):
            raise ReviewContractError("review provenance artifact path escapes store")
        data, _ = _read_structured(path)
        if identity["artifact_id"] not in {str(data.get("id", "")), str(data.get("plan_id", ""))}:
            continue
        for field in ("execution_id", "author_execution_id", "repair_execution_id", "author_execution_ids", "repair_execution_ids"):
            value = data.get(field, [])
            ids.update(str(item) for item in (value if isinstance(value, list) else [value]) if item)
    if stage != "specification":
        bindings = root / ".work-bundle/runtime/execution" / str(identity["artifact_id"])
        for path in bindings.glob("*/execution-binding.json"):
            if not path.resolve().is_relative_to(bindings.resolve()):
                raise ReviewContractError("review provenance binding path escapes store")
            binding = json.loads(path.read_text())
            if binding.get("execution_id"):
                ids.add(str(binding["execution_id"]))
    return ids


def _known_task_execution_ids(root: Path, task_id: str) -> set[str]:
    ids: set[str] = set()
    runtime = root / ".work-bundle/runtime/execution"
    for path in runtime.glob(f"*/{task_id}/execution-binding.json"):
        if not path.resolve().is_relative_to(runtime.resolve()):
            raise ReviewContractError("task review provenance binding path escapes store")
        binding = json.loads(path.read_text())
        for field in ("execution_id",):
            if binding.get(field):
                ids.add(str(binding[field]))
        ownership = binding.get("ownership") if isinstance(binding.get("ownership"), Mapping) else {}
        for field in ("run_id", "agent_id"):
            if ownership.get(field):
                ids.add(str(ownership[field]))
    return ids


def _native_reviewer_module():
    path = Path(__file__).resolve().parents[1] / "work-bundle/reviewer_workspace.py"
    existing = sys.modules.get("reviewer_workspace")
    if existing is not None:
        if Path(existing.__file__).resolve() != path:
            raise ReviewContractError("native reviewer module collision")
        return existing
    spec = importlib.util.spec_from_file_location("reviewer_workspace", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_native_run_proof(receipt, packet, result, path, immutable_file, canonical):
    """Re-derive observed host identity/result from immutable actual run input/output."""
    runtime = _native_reviewer_module()
    try:
        stdout = immutable_file(path.with_suffix(".stdout.jsonl"))
        stderr = immutable_file(path.with_suffix(".stderr.txt"))
        request_bytes = immutable_file(path.with_suffix(".request.json"))
        request = json.loads(request_bytes)
        controller_path = path.with_suffix(".controller.json")
        controller_evidence = (
            json.loads(immutable_file(controller_path)) if controller_path.exists() else None
        )
        combined_evidence = [
            *request.get("evidence", []),
            *(controller_evidence or []),
        ]
        launch = json.loads(immutable_file(path.with_suffix(".launch.json")))
        argv = launch["argv"]
        host_id, worker = runtime.parse_native_reviewer_transcript(stdout.decode(), stderr.decode())
        if (receipt.get("host_run_id") != host_id or receipt.get("isolation") != runtime.NATIVE_ISOLATION
                or receipt.get("stdout_sha256") != hashlib.sha256(stdout).hexdigest()
                or receipt.get("stderr_sha256") != hashlib.sha256(stderr).hexdigest()
                or receipt.get("request_sha256") != hashlib.sha256(request_bytes).hexdigest()
                or receipt.get("argv_sha256") != canonical(argv)
                or receipt.get("executable_sha256") != launch.get("executable_sha256")
                or not SHA256_RE.fullmatch(str(receipt.get("executable_sha256", "")))
                or not Path(argv[0]).is_absolute()
                or argv != runtime._native_reviewer_argv(Path(argv[0]), Path(argv[9]), argv[11])
                or set(request) != {"instructions", "review_input", "evidence"}
                or request["review_input"] != runtime._native_review_input(
                    packet, combined_evidence if controller_evidence is not None else None
                ) or not isinstance(request["instructions"], str)
                or not request["instructions"].strip()):
            raise ValueError("native launch/input mismatch")
        evidence = request["evidence"]
        artifacts = runtime._native_review_artifacts(packet, combined_evidence)
        if len(evidence) != len(artifacts):
            raise ValueError("native input evidence mismatch")
        for expected, actual in zip(artifacts, evidence):
            if (set(actual) != {*expected, "content"} or any(actual[key] != value for key, value in expected.items())
                    or hashlib.sha256(actual["content"].encode()).hexdigest() != expected["sha256"]):
                raise ValueError("native input evidence mismatch")
        if controller_evidence is not None:
            controller_locators = runtime._controller_only_artifact_locators(
                packet, combined_evidence
            )
            controller_artifacts = [
                item for item in packet["artifacts"]
                if item.get("locator") in controller_locators
            ]
            if len(controller_evidence) != len(controller_artifacts):
                raise ValueError("native controller evidence mismatch")
            for expected, actual in zip(controller_artifacts, controller_evidence):
                if (
                    set(actual) != {*expected, "content"}
                    or any(actual[key] != value for key, value in expected.items())
                    or hashlib.sha256(actual["content"].encode()).hexdigest() != expected["sha256"]
                ):
                    raise ValueError("native controller evidence mismatch")
        key = "task_review_context" if result.get("review_target_kind", "stage") == "task" else "stage_review_context"
        context = {**packet[key], "agent_id": host_id, "execution_id": host_id}
        compact = key == "task_review_context" or (context.get("stage") == "integrated_implementation" and "task_review" in worker)
        if compact:
            observed = runtime._task_product_judgment_review(
                worker, review_id=receipt["review_id"], context=context, packet=packet,
                started_at=receipt["started_at"], completed_at=receipt["completed_at"],
                previous_review=result.get("previous_review"), integrated_stage=key == "stage_review_context")
        else:
            observed = runtime._stage_product_judgment_review(
                worker, review_id=receipt["review_id"], context=context, packet=packet,
                started_at=receipt["started_at"], completed_at=receipt["completed_at"],
                previous_review=result.get("previous_review"))
        if observed != result or receipt.get("review_result") != result or receipt.get(key) != context:
            raise ValueError("native judgment/result mismatch")
        frozen_control_evidence: dict[str, str] = {}
        for item in combined_evidence:
            locator = item.get("locator")
            content = item.get("content")
            if not isinstance(locator, str) or not locator.startswith("control:"):
                continue
            if not isinstance(content, str) or locator in frozen_control_evidence:
                raise ValueError("native control evidence is invalid")
            frozen_control_evidence[locator] = content
        return context, frozen_control_evidence
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, runtime.ReviewerWorkspaceError) as error:
        raise ReviewContractError("native reviewer-run provenance does not bind this accepted review") from error


def _validate_reviewer_run(root: Path, review: Mapping[str, Any]) -> None:
    reference = review.get("reviewer_run")
    if not isinstance(reference, dict) or set(reference) != {"run_id", "sha256"}:
        raise ReviewContractError("reviewer-run provenance receipt is required")
    run_id = _identifier(reference["run_id"], "reviewer_run.run_id")
    if not re.fullmatch(r"reviewer-run-[0-9a-f-]{36}", run_id):
        raise ReviewContractError("reviewer-run provenance identity is invalid")
    runtime = reviewer_runtime_root(root).resolve()
    path = runtime / "receipts/reviewer-process" / f"{run_id}.json"
    def immutable_file(target: Path) -> bytes:
        if (target.is_symlink() or not target.resolve().is_relative_to(runtime)
                or not target.is_file() or target.stat().st_mode & 0o222):
            raise ReviewContractError("reviewer-run provenance is missing or mutable")
        return target.read_bytes()
    raw = immutable_file(path)
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ReviewContractError("reviewer-run provenance receipt digest mismatch")
    receipt = _mapping(json.loads(raw), "reviewer-run provenance receipt")
    started = _rfc3339_utc(receipt.get("started_at"), "reviewer receipt started_at")
    completed = _rfc3339_utc(receipt.get("completed_at"), "reviewer receipt completed_at")
    if started > completed or completed > datetime.now(timezone.utc):
        raise ReviewContractError("reviewer-run provenance has invalid completion time")
    packet = _mapping(json.loads(immutable_file(path.with_suffix(".packet.json"))), "reviewer-run provenance packet")
    def canonical(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    result = {key: value for key, value in review.items() if key != "reviewer_run"}
    kind = str(review.get("review_target_kind") or "stage")
    context_key = "task_review_context" if kind == "task" else "stage_review_context"
    context = _mapping(receipt.get(context_key, {}), "reviewer-run provenance context")
    native = receipt.get("schema") == "reviewer-native-receipt-v1"
    packet_context = packet.get(context_key)
    frozen_control_evidence: dict[str, str] = {}
    if native:
        packet_context, frozen_control_evidence = _validate_native_run_proof(
            receipt, packet, result, path, immutable_file, canonical
        )
    mode = "direct_source" if review["evidence"]["mode"] == "direct" else review["evidence"]["mode"]
    review_context = {
        "review_mode": review.get("review_mode", "initial"),
        "review_target_kind": review.get("review_target_kind", "stage"),
        "repair_frontier": review.get("repair_frontier"),
        "review_reset": review.get("review_reset"),
    }
    receipt_context = {
        "review_mode": context.get("review_mode", "initial"),
        "review_target_kind": context.get("review_target_kind", "stage"),
        "repair_frontier": context.get("repair_frontier"),
        "review_reset": context.get("review_reset"),
    }
    if (receipt.get("schema") not in {"reviewer-process-receipt-v1", "reviewer-native-receipt-v1"} or receipt.get("run_id") != run_id
            or receipt.get("review_id") != review["review_id"] or receipt.get("status") != "passed"
            or receipt.get("exit_code") != 0 or receipt.get("review_result_sha256") != canonical(result)
            or receipt.get("packet_sha256") != canonical(packet) or packet_context != context
            or context.get("target_identity") != review["target_identity"]
            or (kind == "stage" and context.get("stage") != review["stage"])
            or context.get("agent_id") != review["reviewer"]["agent_id"]
            or context.get("evidence_mode") != review["reviewer"]["context_origin"]
            or context.get("capability") != review["reviewer"]["capability"] or context.get("evidence_mode") != mode
            or review_context != receipt_context
            or (not native and receipt.get("isolation") != {"mechanism": "sandbox-exec", "network": "denied", "write_scope": "scratch"})
            or not context.get("execution_id")
            or (not native and receipt.get("sandbox_profile_sha256") != hashlib.sha256(immutable_file(path.with_suffix(".profile.sb"))).hexdigest())
            or receipt.get("event_log_sha256") != hashlib.sha256(immutable_file(path.with_suffix(".events.jsonl"))).hexdigest()):
        raise ReviewContractError("reviewer-run provenance does not bind this accepted review")
    known = (
        _known_task_execution_ids(root, str(review["target_identity"]["artifact_id"]))
        if kind == "task"
        else _known_execution_ids(root, str(review["stage"]), review["target_identity"])
    )
    if kind == "stage":
        validate_stage_evidence(
            root,
            context,
            packet,
            frozen_control_evidence=frozen_control_evidence,
        )
    if run_id in known or context["execution_id"] in known:
        raise ReviewContractError("reviewer-run provenance overlaps author/repair execution")


def artifact_review_identity(path: Path, *, content: str | None = None) -> dict[str, Any]:
    """Semantic artifact identity; only lifecycle bookkeeping is non-semantic.

    Body, version, links, validation definitions and all other metadata remain bound.
    This permits the approved status transition without invalidating its own review.
    """
    text = path.read_text(encoding="utf-8") if content is None else content.rstrip() + "\n"
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise SystemExit(f"stage review: missing artifact front matter: {path}")
    raw, body = text[4:].split("\n---\n", 1)
    metadata = parse_yaml_subset(raw)
    if not isinstance(metadata, dict) or not metadata.get("id"):
        raise SystemExit(f"stage review: missing artifact identity: {path}")
    semantic = {key: value for key, value in metadata.items() if key not in {
        "status", "last_updated", "updated_at",
    }}
    payload = json.dumps([semantic, body], sort_keys=True, default=str, separators=(",", ":"))
    return {"artifact_id": str(metadata["id"]), "revision": str(metadata.get("version", "1")),
            "sha256": hashlib.sha256(payload.encode()).hexdigest(), "source_tree": None}


PLAN_APPEND_ONLY_FIELDS = frozenset(
    {
        "accepted_result",
        "accepted_results",
        "accepted_result_reference",
        "accepted_result_references",
        "evidence_reference",
        "evidence_references",
        "review_id",
        "target_identity",
        "review_mode",
        "repair_frontier",
        "review_reset",
    }
)


def _semantic_plan_value(value: Any, *, top_level: bool = False) -> Any:
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        created = value.get("date_created")
        for key, child in sorted(value.items()):
            if key in PLAN_APPEND_ONLY_FIELDS:
                continue
            if top_level and key in {"status", "last_updated", "updated_at"}:
                continue
            if key == "status":
                projected[key] = "Planned"
            elif key in {"last_updated", "updated_at"} and created is not None:
                projected[key] = _semantic_plan_value(created)
            elif key == "verdict":
                projected[key] = "pending"
            elif key == "reviewed_head":
                projected[key] = ""
            elif key == "findings":
                projected[key] = []
            else:
                projected[key] = _semantic_plan_value(child)
        return projected
    if isinstance(value, list):
        return [_semantic_plan_value(child) for child in value]
    return value


def _semantic_plan_body(body: str) -> str:
    """Remove lifecycle closure state while retaining knowledge authority text."""

    section_pattern = re.compile(
        r"^##\s+(?:2\.1\s+)?Knowledge Base Update Carry Forward\s*$"
        r"[\s\S]*?(?=^##\s|\Z)",
        re.MULTILINE,
    )
    closure_pattern = re.compile(
        r"^(?P<prefix>-\s+(?:\*\*Closure\ return\*\*|Closure\ return):[ \t]*)"
        r"(?:missing|completed|not-needed|blocked)(?P<suffix>[ \t]*)$",
        re.MULTILINE,
    )

    def normalize_closure(match: re.Match[str]) -> str:
        return closure_pattern.sub(
            r"\g<prefix>missing\g<suffix>", match.group(0)
        )

    return section_pattern.sub(normalize_closure, body)


def _semantic_plan_artifact(path: Path, *, content: str | None = None) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if content is None else content.rstrip() + "\n"
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise SystemExit(f"stage review: missing artifact front matter: {path}")
    raw, body = text[4:].split("\n---\n", 1)
    metadata = parse_yaml_subset(raw)
    if not isinstance(metadata, dict) or not metadata.get("id"):
        raise SystemExit(f"stage review: missing artifact identity: {path}")
    return {
        "metadata": _semantic_plan_value(metadata, top_level=True),
        "body": _semantic_plan_body(body),
    }


def _semantic_plan_artifact_digest(projection: Mapping[str, Any]) -> str:
    payload = json.dumps(
        [projection["metadata"], projection["body"]],
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _semantic_plan_member_key(plan_root: Path, path: Path) -> str:
    parts = list(path.relative_to(plan_root).parts)
    if parts and parts[0] == "archived":
        parts[0] = "active"
    return Path(*parts).as_posix()


def semantic_plan_projection(
    root: Path, plan_path: Path, *, content: str | None = None
) -> dict[str, Any]:
    """Return the canonical executable projection used by plan review freshness."""

    plan_root = root / ".work-bundle/orchestration/plan"
    if not plan_path.resolve().is_relative_to(plan_root.resolve()):
        raise SystemExit("stage review: root plan escapes plan store")
    root_projection = _semantic_plan_artifact(plan_path, content=content)
    plan_data = root_projection["metadata"]
    plan_id = str(plan_data["id"])
    members = {
        _semantic_plan_member_key(plan_root, plan_path): _semantic_plan_artifact_digest(
            root_projection
        )
    }
    for path in sorted(plan_root.rglob("*.md")):
        if path == plan_path:
            continue
        if not path.resolve().is_relative_to(plan_root.resolve()):
            raise SystemExit("stage review: plan member escapes plan store")
        data, _ = _read_structured(path)
        if str(data.get("plan_id", "")) != plan_id:
            continue
        members[_semantic_plan_member_key(plan_root, path)] = _semantic_plan_artifact_digest(
            _semantic_plan_artifact(path)
        )
    specifications = [
        artifact_review_identity(path) for path in _resolve_spec_paths(root, {}, plan_data)
    ]
    return {
        "members": members,
        "specifications": specifications,
    }


def _require_current_review(root: Path, stage: str, identity: Mapping[str, Any]) -> None:
    """Read native records; historical prose is not an acceptance envelope."""
    accepted = []
    matching_values = []
    review_ids: set[str] = set()
    historical: dict[str, Mapping[str, Any]] = {}
    review_root = root / ".work-bundle/orchestration/reviews"
    try:
        documents = []
        for path in sorted(review_root.rglob("*")):
            if path.suffix not in {".json", ".yaml", ".yml"} or not path.is_file():
                continue
            if not path.resolve().is_relative_to(review_root.resolve()):
                raise ReviewContractError("review record escapes review store")
            value = _read_document(path)
            if not isinstance(value, dict) or "review_id" not in value or "stage" not in value:
                continue
            if value["stage"] == stage:
                review_key = str(value["review_id"])
                if review_key in historical:
                    raise ReviewContractError("stage review IDs must be globally unique")
                historical[review_key] = value
            documents.append(value)
        for value in documents:
            # Old target records remain history, not current acceptance candidates.
            # In particular, a superseded legacy evidence mode must not poison a
            # valid replacement review for the actual current artifact.
            if value["stage"] != stage or value.get("target_identity") != identity:
                continue
            record = _validate_stored_stage_chain(value, historical)
            if record.review_id in review_ids:
                raise ReviewContractError("stage review IDs must be globally unique")
            review_ids.add(record.review_id)
            if record.stage == stage and record.target_identity == identity:
                accepted.append(record)
                matching_values.append(value)
        latest_time = max((_rfc3339_utc(item.completed_at, "completed_at") for item in accepted), default=None)
        latest = [item for item in accepted if _rfc3339_utc(item.completed_at, "completed_at") == latest_time]
        if latest and all(item.verdict == "accepted" and not item.staleness["is_stale"] for item in latest):
            for item in latest:
                value = next(value for value in matching_values if value["review_id"] == item.review_id)
                _validate_reviewer_run(root, value)
            return
    except (ValueError, OSError) as error:
        raise SystemExit(f"stage review blocked: {error}") from error
    raise SystemExit(f"stage review blocked: fresh accepted {stage} review required for {dict(identity)}")


def require_specification_review(root: Path, path: Path, *, content: str | None = None) -> None:
    if not path.resolve().is_relative_to((root / ".work-bundle/orchestration/spec").resolve()):
        raise SystemExit("stage review: specification escapes spec store")
    _require_current_review(root, "specification", artifact_review_identity(path, content=content))


def plan_review_identity(root: Path, plan_path: Path, *, content: str | None = None) -> dict[str, Any]:
    projection = semantic_plan_projection(root, plan_path, content=content)
    identity = artifact_review_identity(plan_path, content=content)
    payload = json.dumps(projection, sort_keys=True, default=str)
    identity["sha256"] = hashlib.sha256(payload.encode()).hexdigest()
    return identity


def require_plan_reviews(root: Path, plan_path: Path, *, source_root: Path | None = None,
                         content: str | None = None) -> None:
    data = (_read_structured(plan_path)[0] if content is None
            else parse_yaml_subset(content.split("---", 2)[1]))
    for spec in _resolve_spec_paths(root, {}, data):
        require_specification_review(root, spec)
    identity = plan_review_identity(root, plan_path, content=content)
    from execution_context import static_plan_task_admission
    static_plan_task_admission(root, plan_path, content=content)
    _require_current_review(root, "plan", identity)
    if source_root is not None:
        def git(*args: str) -> str:
            result = subprocess.run(["git", "-C", str(source_root), *args], capture_output=True, text=True)
            if result.returncode:
                raise SystemExit("stage review: final source repository unavailable")
            return result.stdout.strip()
        if git("status", "--porcelain", "--untracked-files=all"):
            raise SystemExit("stage review: final source must be clean, including untracked files")
        final = dict(identity, source_tree=git("rev-parse", "HEAD^{tree}"))
        _require_current_review(root, "integrated_implementation", final)


@dataclass(frozen=True)
class ReviewFindingV1:
    finding_id: str
    stage: str
    finding_class: str
    severity: str
    first_broken_artifact: str
    obligation_basis: str
    evidence: tuple[Mapping[str, Any], ...]
    target_identity: Mapping[str, Any]
    summary: str
    recommended_owner: str
    disposition: str


@dataclass(frozen=True)
class EvidenceCausalClassificationV1:
    """Agent-authored causal judgment required before evidence can route action."""

    observation_reference: str
    accepted_authority_comparison: Mapping[str, str]
    causal_class: str
    affected_claim: str
    affected_owner: str
    authorized_lifecycle_action: str
    disposition: str


@dataclass(frozen=True)
class StageReviewV1:
    review_id: str
    review_mode: str
    review_target_kind: str
    repair_frontier: Mapping[str, Any] | None
    review_reset: Mapping[str, Any] | None
    stage: str
    target_identity: Mapping[str, Any]
    reviewer: Mapping[str, Any]
    evidence: Mapping[str, Any]
    verdict: str
    findings: tuple[ReviewFindingV1, ...]
    started_at: str
    completed_at: str
    staleness: Mapping[str, Any]


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewContractError(f"{name} must be an object")
    return value


def _closed(record: Mapping[str, Any], required: frozenset[str], name: str) -> None:
    missing = sorted(required - record.keys())
    unknown = sorted(record.keys() - required)
    if missing:
        raise ReviewContractError(f"{name} missing required fields: {', '.join(missing)}")
    if unknown:
        raise ReviewContractError(f"{name} contains unknown fields: {', '.join(unknown)}")


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewContractError(f"{name} must be a non-empty string")
    return value


def _identifier(value: Any, name: str) -> str:
    text = _nonempty(value, name)
    if not ID_RE.fullmatch(text):
        raise ReviewContractError(f"{name} is not a valid id")
    return text


def _enum(value: Any, allowed: frozenset[str] | set[str], name: str) -> str:
    if value not in allowed:
        raise ReviewContractError(f"{name} must be one of: {', '.join(sorted(allowed))}")
    return str(value)


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ReviewContractError(f"{name} must be a list of non-empty strings")
    return value


def _rfc3339_utc(value: Any, name: str) -> datetime:
    text = _nonempty(value, name)
    if not text.endswith("Z"):
        raise ReviewContractError(f"{name} must be RFC3339 UTC")
    try:
        return datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ReviewContractError(f"{name} must be RFC3339 UTC") from error


def _target_identity(value: Any, name: str = "target_identity") -> Mapping[str, Any]:
    target = _mapping(value, name)
    _closed(target, TARGET_KEYS, name)
    _identifier(target["artifact_id"], f"{name}.artifact_id")
    _nonempty(target["revision"], f"{name}.revision")
    if not isinstance(target["sha256"], str) or not SHA256_RE.fullmatch(target["sha256"]):
        raise ReviewContractError(f"{name}.sha256 must be a lowercase SHA-256")
    source_tree = target["source_tree"]
    if source_tree is not None and (not isinstance(source_tree, str) or not GIT_OID_RE.fullmatch(source_tree)):
        raise ReviewContractError(f"{name}.source_tree must be a Git object id or null")
    return target


def review_evidence_identity(value: Mapping[str, Any]) -> str:
    """Return a compact immutable identity for reusable review evidence."""
    record = _mapping(value, "review")
    evidence = _mapping(record.get("evidence"), "evidence")
    payload = {"review_id": record.get("review_id"), "evidence": evidence,
               "reviewer_run": record.get("reviewer_run")}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _repair_frontier(value: Any) -> Mapping[str, Any]:
    frontier = _mapping(value, "repair_frontier")
    _closed(frontier, REPAIR_FRONTIER_KEYS, "repair_frontier")
    _identifier(frontier["prior_review_id"], "repair_frontier.prior_review_id")
    finding_ids = _string_list(frontier["blocking_finding_ids"], "repair_frontier.blocking_finding_ids")
    if not finding_ids or len(finding_ids) != len(set(finding_ids)):
        raise ReviewContractError("repair_frontier.blocking_finding_ids must be non-empty and unique")
    _target_identity(frontier["previous_reviewed_identity"], "repair_frontier.previous_reviewed_identity")
    _target_identity(frontier["repaired_identity"], "repair_frontier.repaired_identity")
    boundaries = _string_list(frontier["affected_boundaries"], "repair_frontier.affected_boundaries")
    if not boundaries or len(boundaries) != len(set(boundaries)):
        raise ReviewContractError("repair_frontier.affected_boundaries must be non-empty and unique")
    reference = frontier["frozen_evidence_reference"]
    if not isinstance(reference, str) or not SHA256_RE.fullmatch(reference):
        raise ReviewContractError("repair_frontier.frozen_evidence_reference must be a lowercase SHA-256")
    return frontier


def _review_reset(value: Any) -> Mapping[str, Any]:
    reset = _mapping(value, "review_reset")
    _closed(reset, REVIEW_RESET_KEYS, "review_reset")
    _identifier(reset["prior_review_id"], "review_reset.prior_review_id")
    _enum(reset["reason_class"], MATERIAL_CHANGE_CLASSES, "review_reset.reason_class")
    _nonempty(reset["reason"], "review_reset.reason")
    return reset


def classify_first_broken_owner(finding_class: str) -> tuple[str, str, str]:
    try:
        return ROUTES[finding_class]
    except KeyError as error:
        raise ReviewContractError(f"class is not classified: {finding_class}") from error


def validate_evidence_causal_classification(
    value: Mapping[str, Any],
) -> EvidenceCausalClassificationV1:
    """Validate an agent's classification; this helper never infers a semantic class."""

    record = _mapping(value, "evidence causal classification")
    _closed(record, EVIDENCE_CAUSAL_CLASSIFICATION_KEYS, "evidence causal classification")
    observation = _nonempty(record["observation_reference"], "observation_reference")
    comparison = _mapping(record["accepted_authority_comparison"], "accepted_authority_comparison")
    _closed(comparison, ACCEPTED_AUTHORITY_COMPARISON_KEYS, "accepted_authority_comparison")
    authority_identity = _nonempty(
        comparison["authority_identity"], "accepted_authority_comparison.authority_identity"
    )
    basis = _nonempty(comparison["basis"], "accepted_authority_comparison.basis")
    causal_class = _enum(record["causal_class"], EVIDENCE_CAUSAL_CLASSES, "causal_class")
    expected_comparison = EVIDENCE_CAUSAL_COMPARISONS[causal_class]
    if comparison["result"] != expected_comparison:
        raise ReviewContractError("accepted authority comparison does not support the causal class")
    affected_claim = _nonempty(record["affected_claim"], "affected_claim")
    affected_owner = _nonempty(record["affected_owner"], "affected_owner")
    expected_action, expected_disposition = EVIDENCE_CAUSAL_ROUTES[causal_class]
    if record["authorized_lifecycle_action"] != expected_action:
        raise ReviewContractError("authorized lifecycle action does not match the causal class")
    if record["disposition"] != expected_disposition:
        raise ReviewContractError("classification disposition does not match the causal class")
    return EvidenceCausalClassificationV1(
        observation_reference=observation,
        accepted_authority_comparison={
            "authority_identity": authority_identity,
            "result": expected_comparison,
            "basis": basis,
        },
        causal_class=causal_class,
        affected_claim=affected_claim,
        affected_owner=affected_owner,
        authorized_lifecycle_action=expected_action,
        disposition=expected_disposition,
    )


def review_remains_current_after_observation(
    classification: Mapping[str, Any], *, reviewed_claim: str
) -> bool:
    """Apply a classification to one review claim without treating raw evidence as authority."""

    record = validate_evidence_causal_classification(classification)
    claim = _nonempty(reviewed_claim, "reviewed_claim")
    return not (
        record.causal_class
        in {"claim_relevant_drift", "implementation_defect", "authority_plan_gap"}
        and record.affected_claim == claim
    )


def _affected_region(value: Any) -> dict[str, list[str]]:
    region = _mapping(value, "affected region")
    _closed(region, AFFECTED_REGION_KEYS, "affected region")
    result: dict[str, list[str]] = {}
    for field in ("task_ids", "interfaces", "validation_oracles"):
        items = _string_list(region[field], f"affected region.{field}")
        if len(items) != len(set(items)) or any(not ID_RE.fullmatch(item) for item in items):
            raise ReviewContractError(f"affected region.{field} must contain unique valid ids")
        result[field] = list(items)
    if not result["task_ids"]:
        raise ReviewContractError("affected region.task_ids must be non-empty")
    paths = _string_list(region["paths"], "affected region.paths")
    if len(paths) != len(set(paths)):
        raise ReviewContractError("affected region.paths must be unique")
    for item in paths:
        path = Path(item)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ReviewContractError("affected region.paths must be canonical relative paths")
    result["paths"] = list(paths)
    return {field: result[field] for field in ("task_ids", "paths", "interfaces", "validation_oracles")}


def _binding_identity(value: Any) -> dict[str, str]:
    identity = _mapping(value, "binding identity")
    _closed(identity, BINDING_IDENTITY_KEYS, "binding identity")
    binding_id = _identifier(identity["binding_id"], "binding identity.binding_id")
    digest = identity["sha256"]
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise ReviewContractError("binding identity.sha256 must be a lowercase SHA-256")
    return {"binding_id": binding_id, "sha256": digest}


def _baseline_identity(value: Any) -> dict[str, str]:
    identity = _mapping(value, "baseline identity")
    _closed(identity, BASELINE_IDENTITY_KEYS, "baseline identity")
    if any(
        not isinstance(identity[field], str) or not GIT_OID_RE.fullmatch(identity[field])
        for field in BASELINE_IDENTITY_KEYS
    ):
        raise ReviewContractError("baseline identity must contain exact Git head and tree ids")
    return {"head": str(identity["head"]), "tree": str(identity["tree"])}


def validate_review_finding(value: Mapping[str, Any]) -> ReviewFindingV1:
    record = _mapping(value, "review_finding_v1")
    _closed(record, FINDING_KEYS, "review_finding_v1")
    finding_id = _identifier(record["finding_id"], "finding_id")
    stage = _enum(record["stage"], FINDING_STAGES, "stage")
    finding_class = _enum(record["class"], set(ROUTES), "class")
    severity = _enum(record["severity"], FINDING_SEVERITIES, "severity")
    obligation_basis = _enum(record["obligation_basis"], OBLIGATION_BASES, "obligation_basis")
    expected_artifact, expected_owner, expected_disposition = classify_first_broken_owner(finding_class)
    if record["first_broken_artifact"] != expected_artifact or record["recommended_owner"] != expected_owner:
        raise ReviewContractError("review finding routing does not match the first broken artifact and owner")
    disposition = _enum(
        record["disposition"],
        {expected_disposition, *TERMINAL_FINDING_DISPOSITIONS},
        "disposition",
    )
    evidence_raw = record["evidence"]
    if not isinstance(evidence_raw, list):
        raise ReviewContractError("evidence must be a list")
    evidence: list[Mapping[str, Any]] = []
    for index, raw_item in enumerate(evidence_raw):
        item = _mapping(raw_item, f"evidence[{index}]")
        _closed(item, EVIDENCE_ITEM_KEYS, f"evidence[{index}]")
        _enum(item["kind"], {"authority", "source", "test", "runtime", "environment"}, f"evidence[{index}].kind")
        for key in ("locator", "digest_or_identity", "observation"):
            _nonempty(item[key], f"evidence[{index}].{key}")
        evidence.append(item)
    if severity == "blocking" and (obligation_basis == "none" or not evidence):
        raise ReviewContractError("blocking finding requires a non-none obligation basis and evidence")
    if finding_class == "advisory_enhancement" and severity == "blocking":
        raise ReviewContractError("advisory_enhancement cannot be blocking without accepted reclassification")
    target = _target_identity(record["target_identity"])
    summary = _nonempty(record["summary"], "summary")
    return ReviewFindingV1(
        finding_id,
        stage,
        finding_class,
        severity,
        expected_artifact,
        obligation_basis,
        tuple(evidence),
        target,
        summary,
        expected_owner,
        disposition,
    )


def _route_review_finding(
    value: Mapping[str, Any], *, previous_scope_expansions: int = 0,
    affected_region: Mapping[str, Any] | None = None,
    unaffected_evidence_identities: Sequence[Mapping[str, Any]] = (),
    original_binding_identity: Mapping[str, Any] | None = None,
    original_baseline_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    finding = validate_review_finding(value)
    expected_action = ROUTES[finding.finding_class][2]
    if finding.disposition in TERMINAL_FINDING_DISPOSITIONS:
        raise ReviewContractError("terminal adjudicator disposition cannot authorize repair mutation")
    if finding.disposition != expected_action:
        raise ReviewContractError("review finding routing disposition is invalid")
    if (
        not isinstance(previous_scope_expansions, int)
        or isinstance(previous_scope_expansions, bool)
        or previous_scope_expansions < 0
    ):
        raise ReviewContractError("previous_scope_expansions must be a non-negative integer")
    result = {
        "finding_id": finding.finding_id,
        "first_broken_artifact": finding.first_broken_artifact,
        "return_to": finding.recommended_owner,
        "action": expected_action,
        "execution_state": (
            "paused_for_reslice" if expected_action == "reslice_plan" else "returned_for_repair"
        ),
        "preserve_valid_work_and_evidence": True,
        "silent_expansion_allowed": False,
    }
    if expected_action != "reslice_plan":
        if (
            affected_region is not None
            or unaffected_evidence_identities
            or original_binding_identity is not None
            or original_baseline_identity is not None
        ):
            raise ReviewContractError("affected region applies only to a plan reslice")
        return result

    region = _affected_region(affected_region)
    binding = _binding_identity(original_binding_identity)
    baseline = _baseline_identity(original_baseline_identity)
    preserved = [
        dict(_target_identity(item, "unaffected_evidence_identity"))
        for item in unaffected_evidence_identities
    ]
    preserved_ids = [item["artifact_id"] for item in preserved]
    if len(preserved_ids) != len(set(preserved_ids)) or set(region["task_ids"]).intersection(preserved_ids):
        raise ReviewContractError("affected region and unaffected evidence must be disjoint and unambiguous")
    result.update(
        {
            "affected_region": region,
            "returned_authority_identity": dict(finding.target_identity),
            "preserved_evidence_identities": preserved,
            "resume_requires": "accepted_repaired_plan_authority",
            "original_binding_identity": binding,
            "original_baseline_identity": baseline,
        }
    )
    return result


def _validated_review_envelope(value: Mapping[str, Any]) -> StageReviewV1:
    """Validate one bounded task-or-stage review without walking older history."""

    if value.get("review_target_kind") == "task":
        return validate_task_acceptance_review(value)
    previous = value.get("previous_review")
    envelope = {key: item for key, item in value.items() if key != "previous_review"}
    current = validate_stage_review(envelope)
    if current.review_mode == "repair":
        if not isinstance(previous, Mapping) or "previous_review" in previous:
            raise ReviewContractError("stage repair review requires exactly one previous_review")
        return validate_review_sequence(envelope, previous_review=previous)
    if current.review_reset is not None:
        if not isinstance(previous, Mapping) or "previous_review" in previous:
            raise ReviewContractError("stage reset review requires exactly one previous_review")
        return validate_review_sequence(
            envelope,
            previous_review=previous,
            material_change=str(current.review_reset["reason_class"]),
        )
    return validate_review_sequence(envelope)


def _bounded_stage_predecessor(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project one stored predecessor without recursively embedding its history."""

    return {key: item for key, item in value.items() if key != "previous_review"}


def _stage_review_predecessor_id(record: StageReviewV1) -> str | None:
    if record.review_mode == "repair":
        assert record.repair_frontier is not None
        return str(record.repair_frontier["prior_review_id"])
    if record.review_reset is not None:
        return str(record.review_reset["prior_review_id"])
    return None


def _validate_stored_stage_chain(
    value: Mapping[str, Any],
    historical: Mapping[str, Mapping[str, Any]],
    *,
    visiting: frozenset[str] = frozenset(),
) -> StageReviewV1:
    """Validate bounded predecessor projections against complete stored history."""

    record = _validated_review_envelope(value)
    review_id = record.review_id
    if review_id in visiting:
        raise ReviewContractError("stage review predecessor chain contains a cycle")
    predecessor_id = _stage_review_predecessor_id(record)
    if predecessor_id is None:
        return record
    predecessor = historical.get(predecessor_id)
    if predecessor is None:
        raise ReviewContractError("stage re-review predecessor is missing")
    _validate_stored_stage_chain(
        predecessor,
        historical,
        visiting=visiting | {review_id},
    )
    supplied = value.get("previous_review")
    if supplied != _bounded_stage_predecessor(predecessor):
        raise ReviewContractError(
            "stage re-review predecessor projection does not match stored predecessor"
        )
    return record


def _stored_stage_history(root: Path, stage: str) -> dict[str, Mapping[str, Any]]:
    review_root = root.expanduser().resolve() / ".work-bundle/orchestration/reviews"
    historical: dict[str, Mapping[str, Any]] = {}
    for path in sorted(review_root.rglob("*")):
        if path.suffix not in {".json", ".yaml", ".yml"} or not path.is_file():
            continue
        if not path.resolve().is_relative_to(review_root.resolve()):
            raise ReviewContractError("review record escapes review store")
        value = _read_document(path)
        if not isinstance(value, dict) or value.get("stage") != stage or "review_id" not in value:
            continue
        review_id = str(value["review_id"])
        if review_id in historical:
            raise ReviewContractError("stage review IDs must be globally unique")
        historical[review_id] = value
    return historical


def _review_store_path(root: Path, review_id: str) -> Path:
    store = root.expanduser().resolve() / ".work-bundle/orchestration/reviews"
    path = (store / f"{_identifier(review_id, 'review_id')}.json").resolve(strict=False)
    if not path.is_relative_to(store.resolve()):
        raise ReviewContractError("stored review path escapes review store")
    return path


def publish_review(
    root: Path,
    review: Mapping[str, Any],
    *,
    current_target_identity: Mapping[str, Any],
) -> dict[str, str]:
    """Publish a natively receipted current task-or-stage review exactly once."""

    record = dict(_mapping(review, "review publication"))
    validated = _validated_review_envelope(record)
    if record.get("review_target_kind", "stage") == "stage" and _stage_review_predecessor_id(validated):
        validated = _validate_stored_stage_chain(
            record, _stored_stage_history(root, validated.stage)
        )
    current = dict(_target_identity(current_target_identity, "current_target_identity"))
    if validated.target_identity != current:
        raise ReviewContractError("review publication target is not current")
    _validate_reviewer_run(root.expanduser().resolve(), record)
    path = _review_store_path(root, validated.review_id)
    content = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != content:
            raise ReviewContractError("stored review identity collision")
    else:
        with path.open("xb") as stream:
            stream.write(content)
        path.chmod(0o444)
    return {"review_id": validated.review_id, "sha256": digest}


def load_stored_review(
    root: Path,
    reference: Mapping[str, Any],
    *,
    current_target_identity: Mapping[str, Any],
) -> tuple[dict[str, Any], StageReviewV1]:
    """Load stored review authority and revalidate its receipt and current target."""

    if not isinstance(reference, Mapping) or set(reference) != {"review_id", "sha256"}:
        raise ReviewContractError("stored review reference is required")
    path = _review_store_path(root, str(reference.get("review_id") or ""))
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_mode & 0o222
    ):
        raise ReviewContractError("stored review is missing or mutable")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference.get("sha256"):
        raise ReviewContractError("stored review digest mismatch")
    record = dict(_mapping(json.loads(raw), "stored review"))
    validated = _validated_review_envelope(record)
    if record.get("review_target_kind", "stage") == "stage" and _stage_review_predecessor_id(validated):
        validated = _validate_stored_stage_chain(
            record, _stored_stage_history(root, validated.stage)
        )
    current = dict(_target_identity(current_target_identity, "current_target_identity"))
    if validated.target_identity != current:
        raise ReviewContractError("stored review target is not current")
    _validate_reviewer_run(root.expanduser().resolve(), record)
    return record, validated


def stored_review_target_identity(
    root: Path, reference: Mapping[str, Any]
) -> dict[str, Any]:
    """Read only a digest-bound target hint; this does not admit review authority."""

    if not isinstance(reference, Mapping) or set(reference) != {"review_id", "sha256"}:
        raise ReviewContractError("stored review reference is required")
    path = _review_store_path(root, str(reference.get("review_id") or ""))
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise ReviewContractError("stored review is missing or mutable")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference.get("sha256"):
        raise ReviewContractError("stored review digest mismatch")
    record = _mapping(json.loads(raw), "stored review")
    return dict(_target_identity(record.get("target_identity"), "stored review target_identity"))


def route_stored_review_verdict(
    root: Path,
    review_reference: Mapping[str, Any],
    *,
    current_target_identity: Mapping[str, Any],
    finding_id: str | None = None,
    previous_scope_expansions: int = 0,
    affected_region: Mapping[str, Any] | None = None,
    unaffected_evidence_identities: Sequence[Mapping[str, Any]] = (),
    original_binding_identity: Mapping[str, Any] | None = None,
    original_baseline_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose a verdict or route one finding only from stored current authority."""

    record, validated = load_stored_review(
        root, review_reference, current_target_identity=current_target_identity
    )
    if finding_id is None:
        return {
            "review_id": validated.review_id,
            "verdict": validated.verdict,
            "target_identity": dict(validated.target_identity),
        }
    matches = [
        item for item in record.get("findings", [])
        if isinstance(item, Mapping) and item.get("finding_id") == finding_id
    ]
    if len(matches) != 1:
        raise ReviewContractError("stored review does not contain exactly one selected finding")
    return _route_review_finding(
        matches[0],
        previous_scope_expansions=previous_scope_expansions,
        affected_region=affected_region,
        unaffected_evidence_identities=unaffected_evidence_identities,
        original_binding_identity=original_binding_identity,
        original_baseline_identity=original_baseline_identity,
    )


# The public legacy name now enforces stored authority too. Pure classification tests
# use the explicitly private helper and cannot be mistaken for lifecycle routing.
route_review_verdict = route_stored_review_verdict


def resume_plan_return(
    value: Mapping[str, Any], *,
    workspace_root: Path,
    plan_path: Path,
    current_binding_identity: Mapping[str, Any],
    current_baseline_identity: Mapping[str, Any],
    current_unaffected_evidence_identities: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Admit a paused affected region only from repaired authority and unchanged evidence."""

    record = _mapping(value, "plan_return")
    _closed(record, PLAN_RETURN_KEYS, "plan_return")
    _identifier(record["finding_id"], "plan_return.finding_id")
    if (
        record["first_broken_artifact"] != "plan"
        or record["return_to"] != "plan_owner"
        or record["action"] != "reslice_plan"
        or record["execution_state"] != "paused_for_reslice"
        or record["resume_requires"] != "accepted_repaired_plan_authority"
        or record["preserve_valid_work_and_evidence"] is not True
        or record["silent_expansion_allowed"] is not False
    ):
        raise ReviewContractError("plan return is not a paused bounded reslice")
    region = _affected_region(record["affected_region"])
    original_binding = _binding_identity(record["original_binding_identity"])
    original_baseline = _baseline_identity(record["original_baseline_identity"])
    if _binding_identity(current_binding_identity) != original_binding:
        raise ReviewContractError("original binding identity changed during bounded reslice")
    if _baseline_identity(current_baseline_identity) != original_baseline:
        raise ReviewContractError("original baseline identity changed during bounded reslice")
    returned = dict(
        _target_identity(record["returned_authority_identity"], "returned_authority_identity")
    )
    try:
        repaired = dict(plan_review_identity(Path(workspace_root), Path(plan_path)))
        _require_current_review(Path(workspace_root), "plan", repaired)
    except (OSError, SystemExit, ValueError) as error:
        raise ReviewContractError(
            "resume requires current accepted repaired plan-review authority"
        ) from error
    if repaired["artifact_id"] != returned["artifact_id"] or repaired == returned:
        raise ReviewContractError("resume requires new accepted repaired authority")

    preserved = [
        dict(_target_identity(item, "preserved_evidence_identity"))
        for item in record["preserved_evidence_identities"]
    ]
    preserved_ids = [item["artifact_id"] for item in preserved]
    if len(preserved_ids) != len(set(preserved_ids)) or set(region["task_ids"]).intersection(preserved_ids):
        raise ReviewContractError("affected region and unaffected evidence must be disjoint and unambiguous")
    current = [
        dict(_target_identity(item, "current_unaffected_evidence_identity"))
        for item in current_unaffected_evidence_identities
    ]
    if current != preserved:
        raise ReviewContractError("unaffected evidence identities changed during bounded reslice")
    resumed = dict(record)
    resumed["execution_state"] = "ready_from_repaired_authority"
    resumed["returned_authority_identity"] = repaired
    return resumed


def transition_review_finding(
    value: Mapping[str, Any], disposition: str
) -> ReviewFindingV1:
    finding = validate_review_finding(value)
    if finding.disposition in TERMINAL_FINDING_DISPOSITIONS:
        raise ReviewContractError("terminal review finding disposition cannot transition")
    if disposition not in TERMINAL_FINDING_DISPOSITIONS:
        raise ReviewContractError("finding lifecycle transition requires an adjudicator disposition")
    updated = dict(value)
    updated["disposition"] = disposition
    return validate_review_finding(updated)


def validate_stage_review(
    value: Mapping[str, Any], *, current_target_identity: Mapping[str, Any] | None = None
) -> StageReviewV1:
    record = _mapping(value, "stage_review_v1")
    envelope = {key: item for key, item in record.items() if key != "reviewer_run"}
    keys = set(envelope)
    if not LEGACY_STAGE_REVIEW_KEYS.issubset(keys) or not keys.issubset(STAGE_REVIEW_KEYS):
        _closed(envelope, STAGE_REVIEW_KEYS, "stage_review_v1")
    if "reviewer_run" in record:
        reference = _mapping(record["reviewer_run"], "reviewer_run")
        _closed(reference, frozenset({"run_id", "sha256"}), "reviewer_run")
        _identifier(reference["run_id"], "reviewer_run.run_id")
        if not isinstance(reference["sha256"], str) or not SHA256_RE.fullmatch(reference["sha256"]):
            raise ReviewContractError("reviewer_run.sha256 must be a lowercase SHA-256")
    review_id = _identifier(record["review_id"], "review_id")
    review_mode = _enum(record.get("review_mode", "initial"), REVIEW_MODES, "review_mode")
    review_target_kind = _enum(record.get("review_target_kind", "stage"), REVIEW_TARGET_KINDS, "review_target_kind")
    raw_frontier = record.get("repair_frontier")
    raw_reset = record.get("review_reset")
    if review_mode == "repair":
        if raw_frontier is None:
            raise ReviewContractError("repair review requires repair_frontier")
        if raw_reset is not None:
            raise ReviewContractError("repair review cannot carry review_reset; require a fresh initial review")
        repair_frontier = _repair_frontier(raw_frontier)
        review_reset = None
    else:
        if raw_frontier is not None:
            raise ReviewContractError("initial review cannot carry repair_frontier")
        repair_frontier = None
        review_reset = _review_reset(raw_reset) if raw_reset is not None else None
    stage = _enum(record["stage"], STAGE_REVIEW_STAGES, "stage")
    if review_target_kind != "stage":
        raise ReviewContractError("stage_review_v1 review_target_kind must be stage")
    target = _target_identity(record["target_identity"])
    if repair_frontier is not None and repair_frontier["repaired_identity"] != target:
        raise ReviewContractError("repair frontier repaired identity must equal target_identity")
    reviewer = _mapping(record["reviewer"], "reviewer")
    _closed(reviewer, REVIEWER_KEYS, "reviewer")
    _identifier(reviewer["agent_id"], "reviewer.agent_id")
    _enum(reviewer["capability"], {"standard", "judgment"}, "reviewer.capability")
    for field in PARTICIPATION_FIELDS:
        _enum(reviewer[field], {"none", "present"}, f"reviewer.{field}")
    _enum(reviewer["context_origin"], {"direct_source", "reproducible_snapshot", "packet_only", "carried_summary"}, "reviewer.context_origin")

    evidence = _mapping(record["evidence"], "evidence")
    _closed(evidence, REVIEW_EVIDENCE_KEYS, "evidence")
    _enum(evidence["mode"], {"direct_source", "reproducible_snapshot", "packet_only", "direct", "constrained_direct"}, "evidence.mode")
    _string_list(evidence["capabilities"], "evidence.capabilities")
    _string_list(evidence["unavailable_evidence"], "evidence.unavailable_evidence")
    commands = evidence["commands"]
    artifacts = evidence["artifacts"]
    if not isinstance(commands, list) or not isinstance(artifacts, list):
        raise ReviewContractError("evidence commands and artifacts must be lists")
    for index, raw_command in enumerate(commands):
        command = _mapping(raw_command, f"evidence.commands[{index}]")
        _closed(command, COMMAND_KEYS, f"evidence.commands[{index}]")
        _identifier(command["command_id"], f"evidence.commands[{index}].command_id")
        _nonempty(command["purpose"], f"evidence.commands[{index}].purpose")
        if not isinstance(command["exit_code"], int) or isinstance(command["exit_code"], bool):
            raise ReviewContractError(f"evidence.commands[{index}].exit_code must be an integer")
        if not isinstance(command["output_digest"], str) or not SHA256_RE.fullmatch(command["output_digest"]):
            raise ReviewContractError(f"evidence.commands[{index}].output_digest must be a lowercase SHA-256")
    for index, raw_artifact in enumerate(artifacts):
        artifact = _mapping(raw_artifact, f"evidence.artifacts[{index}]")
        _closed(artifact, ARTIFACT_KEYS, f"evidence.artifacts[{index}]")
        _nonempty(artifact["path"], f"evidence.artifacts[{index}].path")
        if not isinstance(artifact["sha256"], str) or not SHA256_RE.fullmatch(artifact["sha256"]):
            raise ReviewContractError(f"evidence.artifacts[{index}].sha256 must be a lowercase SHA-256")

    verdict = _enum(record["verdict"], REVIEW_VERDICTS, "verdict")
    findings_raw = record["findings"]
    if not isinstance(findings_raw, list):
        raise ReviewContractError("findings must be a list")
    findings = tuple(validate_review_finding(_mapping(item, "finding")) for item in findings_raw)
    started = _rfc3339_utc(record["started_at"], "started_at")
    completed = _rfc3339_utc(record["completed_at"], "completed_at")
    if completed < started:
        raise ReviewContractError("completed_at must not precede started_at")
    staleness = _mapping(record["staleness"], "staleness")
    _closed(staleness, STALENESS_KEYS, "staleness")
    if not isinstance(staleness["is_stale"], bool):
        raise ReviewContractError("staleness.is_stale must be boolean")
    reason = staleness["reason"]
    supersedes = staleness["supersedes"]
    if reason is not None:
        _nonempty(reason, "staleness.reason")
    if supersedes is not None:
        _identifier(supersedes, "staleness.supersedes")
    if staleness["is_stale"] and reason is None:
        raise ReviewContractError("stale review requires staleness.reason")
    if not staleness["is_stale"] and reason is not None:
        raise ReviewContractError("current review cannot carry a staleness.reason")
    if current_target_identity is not None:
        current = _target_identity(current_target_identity, "current_target_identity")
        changed = any(target[key] != current[key] for key in TARGET_KEYS)
        if changed and not staleness["is_stale"]:
            raise ReviewContractError("review target changed and the review must be stale")
        if not changed and staleness["is_stale"]:
            raise ReviewContractError("review target is unchanged but the review is marked stale")
    if verdict == "accepted":
        blocking = [item.finding_id for item in findings if item.severity == "blocking"]
        if blocking:
            raise ReviewContractError("accepted review cannot contain blocking findings")
        for field in PARTICIPATION_FIELDS:
            if reviewer[field] != "none":
                raise ReviewContractError(f"accepted review requires reviewer.{field}: none")
        if reviewer["context_origin"] not in {"direct_source", "reproducible_snapshot"}:
            raise ReviewContractError("accepted review requires direct_source or reproducible_snapshot context")
        if evidence["mode"] in {"packet_only", "constrained_direct"} or evidence["unavailable_evidence"]:
            raise ReviewContractError("accepted review requires complete claim-relevant evidence, not packet-only or constrained evidence")
        if evidence["mode"] == "reproducible_snapshot" or reviewer["context_origin"] == "reproducible_snapshot":
            if evidence["mode"] != "reproducible_snapshot" or not artifacts:
                raise ReviewContractError("snapshot review requires explicit reproducible_snapshot artifacts")
    return StageReviewV1(
        review_id,
        review_mode,
        review_target_kind,
        repair_frontier,
        review_reset,
        stage,
        target,
        reviewer,
        evidence,
        verdict,
        findings,
        str(record["started_at"]),
        str(record["completed_at"]),
        staleness,
    )


def validate_review_sequence(
    value: Mapping[str, Any], *, previous_review: Mapping[str, Any] | None = None,
    material_change: str | None = None,
    _task_owned_finding_subset: bool = False,
) -> StageReviewV1:
    """Bind a re-review to its exact predecessor without replaying history."""
    current = validate_stage_review(value)
    if previous_review is None:
        if current.review_mode == "repair" or current.review_reset is not None:
            raise ReviewContractError("re-review requires the exact previous review")
        return current
    previous = validate_stage_review(previous_review)
    if current.review_mode == "repair":
        if material_change is not None:
            _enum(material_change, MATERIAL_CHANGE_CLASSES, "material_change")
            raise ReviewContractError("material change requires a fresh initial review")
        frontier = current.repair_frontier
        assert frontier is not None
        if previous.verdict != "repair" or frontier["prior_review_id"] != previous.review_id:
            raise ReviewContractError("repair frontier must bind the exact prior repair review")
        if frontier["previous_reviewed_identity"] != previous.target_identity:
            raise ReviewContractError("repair frontier previous reviewed identity does not match prior review")
        blocking_findings = {
            item.finding_id: item for item in previous.findings if item.severity == "blocking"
        }
        selected_findings = set(frontier["blocking_finding_ids"])
        if _task_owned_finding_subset:
            if not selected_findings.issubset(blocking_findings):
                raise ReviewContractError(
                    "task repair frontier contains unknown blocking finding IDs"
                )
            if any(
                blocking_findings[finding_id].recommended_owner != "task_owner"
                or blocking_findings[finding_id].disposition != "repair_task"
                for finding_id in selected_findings
            ):
                raise ReviewContractError(
                    "task repair frontier may select only task-owned blocking findings"
                )
        elif selected_findings != set(blocking_findings):
            raise ReviewContractError("repair frontier blocking finding IDs do not match prior review")
        if frontier["frozen_evidence_reference"] != review_evidence_identity(previous_review):
            raise ReviewContractError("repair frontier frozen evidence reference does not match prior review")
        return current
    if material_change is not None:
        _enum(material_change, MATERIAL_CHANGE_CLASSES, "material_change")
        reset = current.review_reset
        if (reset is None or reset["prior_review_id"] != previous.review_id
                or reset["reason_class"] != material_change):
            raise ReviewContractError("material change requires a recorded fresh initial review reset")
        if current.reviewer["capability"] != "judgment":
            raise ReviewContractError("reset requires a capable independent judgment reviewer")
    elif current.review_reset is not None:
        raise ReviewContractError("review_reset requires a classified material change")
    return current


def _task_review_as_stage(value: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt the existing task acceptance record to the native review validator."""
    record = _mapping(value, "task acceptance_review")
    verdict = {"accept": "accepted", "repair": "repair", "blocked": "blocked"}.get(record.get("verdict"))
    if verdict is None:
        raise ReviewContractError("task acceptance_review verdict must be accept, repair, or blocked")
    return {
        "review_id": record.get("review_id"),
        "review_mode": record.get("review_mode"),
        "review_target_kind": "stage",
        "repair_frontier": record.get("repair_frontier"),
        "review_reset": record.get("review_reset"),
        # This is an adapter discriminator, not a fourth stage-review seat.
        "stage": "plan",
        "target_identity": record.get("target_identity"),
        "reviewer": record.get("reviewer"),
        "evidence": record.get("evidence"),
        "verdict": verdict,
        "findings": record.get("findings"),
        "started_at": record.get("started_at"),
        "completed_at": record.get("completed_at"),
        "staleness": record.get("staleness"),
        **({"reviewer_run": record["reviewer_run"]} if "reviewer_run" in record else {}),
    }


def validate_task_acceptance_review(value: Mapping[str, Any]) -> StageReviewV1:
    """Validate a task acceptance review and its one bounded predecessor."""
    record = _mapping(value, "task acceptance_review")
    current = validate_task_review_record(record)
    mode = current.review_mode
    previous = record.get("previous_review")
    if mode == "repair":
        if not isinstance(previous, Mapping):
            raise ReviewContractError("task repair review requires its exact previous_review")
        if "previous_review" in previous:
            raise ReviewContractError("task repair review may carry exactly one previous_review; older history stays lazy")
        if previous.get("review_target_kind") == "stage":
            validated_previous = validate_stage_review(previous)
            if validated_previous.stage != "integrated_implementation":
                raise ReviewContractError(
                    "task repair review stage predecessor must be integrated_implementation"
                )
            return validate_review_sequence(
                _task_review_as_stage(record),
                previous_review=previous,
                _task_owned_finding_subset=True,
            )
        validate_task_review_record(previous)
        return validate_review_sequence(_task_review_as_stage(record), previous_review=_task_review_as_stage(previous))
    if record.get("review_reset") is not None:
        if not isinstance(previous, Mapping):
            raise ReviewContractError("task initial reset requires its exact previous_review")
        validate_task_review_record(previous)
        reset = _mapping(record["review_reset"], "review_reset")
        return validate_review_sequence(
            _task_review_as_stage(record), previous_review=_task_review_as_stage(previous), material_change=str(reset.get("reason_class"))
        )
    return validate_review_sequence(_task_review_as_stage(record))


def validate_task_review_record(value: Mapping[str, Any]) -> StageReviewV1:
    """Validate one native task-review record without traversing history."""
    record = _mapping(value, "task acceptance_review")
    if (record.get("required") is not True or record.get("review_target_kind") != "task"
            or record.get("reviewer_independent") is not True):
        raise ReviewContractError(
            "task acceptance_review requires required: true, reviewer_independent: true, and review_target_kind: task"
        )
    _enum(record.get("review_mode"), REVIEW_MODES, "task acceptance_review.review_mode")
    return validate_stage_review(_task_review_as_stage(record))


def validate_stage_reviews(
    values: Sequence[Mapping[str, Any]], *,
    current_target_identities: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, StageReviewV1]:
    if current_target_identities is None or set(current_target_identities) != STAGE_REVIEW_STAGES:
        raise ReviewContractError("actual current target identities are required for all three stages")
    records = [validate_stage_review(value) for value in values]
    ids = [record.review_id for record in records]
    if len(ids) != len(set(ids)):
        raise ReviewContractError("stage review IDs must be globally unique")
    raw_by_id = {record.review_id: value for record, value in zip(records, values)}
    sequenced = []
    for record, value in zip(records, values):
        if record.review_mode == "repair":
            assert record.repair_frontier is not None
            prior = raw_by_id.get(str(record.repair_frontier["prior_review_id"]))
            if prior is None:
                raise ReviewContractError("repair review predecessor is missing")
            record = validate_review_sequence(value, previous_review=prior)
        elif record.review_reset is not None:
            prior = raw_by_id.get(str(record.review_reset["prior_review_id"]))
            if prior is None:
                raise ReviewContractError("initial review reset predecessor is missing")
            record = validate_review_sequence(
                value, previous_review=prior, material_change=str(record.review_reset["reason_class"])
            )
        sequenced.append(record)
    countable: dict[str, StageReviewV1] = {}
    for record in sorted((item for item in sequenced if item.review_target_kind == "stage"), key=lambda item: item.completed_at):
        current = _target_identity(current_target_identities[record.stage], "current_target_identity")
        if record.target_identity == current:
            countable.pop(record.stage, None)
        if record.verdict == "accepted" and record.staleness["is_stale"] is False and record.target_identity == current:
            countable[record.stage] = record
    if set(countable) != STAGE_REVIEW_STAGES or len(countable) != 3:
        raise ReviewContractError("exactly three mandatory stage identities must have current accepted reviews")
    return countable


def validate_contract_instance(definition: str, value: Mapping[str, Any]) -> ReviewFindingV1 | StageReviewV1:
    if definition in {"reviewFinding", "review_finding_v1", "API-001"}:
        return validate_review_finding(value)
    if definition in {"stageReview", "stage_review_v1", "API-002"}:
        return validate_stage_review(value)
    raise ReviewContractError(f"unsupported contract definition: {definition}")


def _read_document(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as error:
            raise ReviewContractError("YAML input requires PyYAML") from error
        value = yaml.safe_load(text)
    return _mapping(value, str(path))


def _validate_schema_definition(schema: Mapping[str, Any], definition: str, value: Mapping[str, Any]) -> None:
    definitions = _mapping(schema.get("$defs"), "$defs")
    if definition not in definitions:
        raise ReviewContractError(f"schema definition not found: {definition}")
    if definition in {"reviewFinding", "stageReview"}:
        validate_contract_instance(definition, value)
    try:
        from jsonschema import Draft202012Validator
    except ImportError as error:
        if definition in {"reviewFinding", "stageReview"}:
            return
        raise ReviewContractError(f"contract definition requires jsonschema: {definition}") from error
    document = dict(schema)
    document["$ref"] = f"#/$defs/{definition}"
    errors = sorted(Draft202012Validator(document).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        raise ReviewContractError(errors[0].message)


def cmd_validate_contract(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="review_runtime.py validate-contract")
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--definition", required=True)
    parser.add_argument("--instance", type=Path, required=True)
    parsed = parser.parse_args(argv)
    try:
        schema = _read_document(parsed.schema)
        instance = _read_document(parsed.instance)
        _validate_schema_definition(schema, parsed.definition, instance)
    except (OSError, ReviewContractError) as error:
        print(json.dumps({"status": "blocked", "failure_code": "WB_REVIEW_CONTRACT_INVALID", "detail": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"status": "passed", "definition": parsed.definition, "instance": str(parsed.instance)}, sort_keys=True))
    return 0


def cmd_assert_migration_stop(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="review_runtime.py assert-migration-stop")
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--required-excluded", nargs="+", required=True)
    parsed = parser.parse_args(argv)
    try:
        instance = _read_document(parsed.instance)
        if instance.get("issue") != "WOR-107":
            raise ReviewContractError("migration handoff issue must be WOR-107")
        excluded = instance.get("excluded_work")
        if not isinstance(excluded, list) or any(not isinstance(item, str) for item in excluded):
            raise ReviewContractError("excluded_work must be a list of strings")
        missing = [item for item in parsed.required_excluded if item not in excluded]
        if missing:
            raise ReviewContractError(f"migration stop boundary missing exclusions: {', '.join(missing)}")
    except (OSError, ReviewContractError) as error:
        print(json.dumps({"status": "blocked", "failure_code": "WB_MIGRATION_STOP_BOUNDARY_INVALID", "detail": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"status": "passed", "issue": "WOR-107", "excluded_work": parsed.required_excluded}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review_runtime.py")
    parser.add_argument("command", choices=("validate-contract", "assert-migration-stop"))
    parsed, remaining = parser.parse_known_args(argv)
    if parsed.command == "validate-contract":
        return cmd_validate_contract(remaining)
    return cmd_assert_migration_stop(remaining)


if __name__ == "__main__":
    raise SystemExit(main())
