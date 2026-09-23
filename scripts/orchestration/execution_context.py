#!/usr/bin/env python3
"""Compile disposable, task-bounded executor and reviewer context packets."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


# Both CLI families contain a top-level ``core.py``.  Mixed-process harnesses
# must bind this module and its downstream imports to the orchestration sibling.
_CORE_PATH = Path(__file__).with_name("core.py").resolve()
_loaded_core = sys.modules.get("core")
if _loaded_core is None or Path(str(getattr(_loaded_core, "__file__", ""))).resolve() != _CORE_PATH:
    _core_spec = importlib.util.spec_from_file_location("core", _CORE_PATH)
    if _core_spec is None or _core_spec.loader is None:
        raise ImportError("cannot load orchestration core")
    _loaded_core = importlib.util.module_from_spec(_core_spec)
    sys.modules["core"] = _loaded_core
    _core_spec.loader.exec_module(_loaded_core)

from core import _member_roots, resolve_workspace_root
from artifact_inputs import _read_structured, _as_list, _input_path, _resolve_spec_paths
from artifact_store import (
    atomic_write_bytes,
    canonical_artifact_path,
    family_policy,
    load_catalog,
    read_artifact,
    read_yaml_mapping,
    rebuild_index,
)
from repository_preflight import capture_repository_evidence
from task_ownership import (
    canonical_relative_path,
    OwnershipBlocker,
)
from review_identity import source_obligation_records


SOURCE_ID_TOKEN = r"[A-Z][A-Z0-9_-]*-\d+[A-Z]?"
SOURCE_ID_RE = re.compile(rf"^{SOURCE_ID_TOKEN}$")
AUTH_ALIAS_RE = re.compile(r"^AUTH-\d{3}$")
EXCELLENCE_PROPOSAL_RE = re.compile(r"^EXC-\d+$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PLAN_CATALOG = Path(__file__).resolve().parents[2] / "references/assets/orchestration/contract/artifact-family-catalog-v6.yaml"
SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[_-])(credential_values?|password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)(?:$|[_-])",
    re.IGNORECASE,
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(credential_values?|password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)"
    r"\s*[:=]\s*(?!<redacted>(?:\s|$)|null\b|none\b|false\b|true\b)([^\s,}\]]+)"
)
MAX_DIFF_BYTES = 120_000
MAX_DIFF_LINES = 4_000
WORKTREE_REFS = {"worktree", "working-tree", "working_tree"}
TRUTH_BASIS_FIELDS = (
    "purpose",
    "as_is_evidence",
    "decision_authority",
    "expected_delta",
    "conflict_status",
)
KNOWLEDGE_DISPOSITION_ACTIONS = {"none", "update", "supersede", "reclassify"}
EVIDENCE_CAPABILITY_RESULTS = {"mapped", "no_validation_bearing_obligation"}
EVIDENCE_BOUNDARIES = {"unit", "component", "integration", "runtime", "ui_visual", "performance", "accessibility", "inspection", "other"}
EVIDENCE_CLOSURE_RESULTS = {"pending", "passed", "incapable", "contradictory", "stale", "wrong_boundary", "failed", "missing", "unexecuted"}
EVIDENCE_REPAIR_OWNERS = {
    "pending": "task",
    "incapable": "plan",
    "contradictory": "specification",
    "stale": "task",
    "wrong_boundary": "plan",
    "failed": "task",
    "missing": "plan",
    "unexecuted": "task",
}
CONTEXT_EXPANSION_REASONS = {
    None,
    "failed_validation",
    "ambiguity",
    "reviewer_request",
    "authority_gap",
}


class AcceptanceOwnershipError(SystemExit):
    """A completed result failed mandatory harness-owned ownership evidence."""


class _SemanticReference(str):
    """Legacy in-memory semantic view that serializes as its stable ID."""

    def __new__(cls, semantic: str, reference_id: str):
        value = super().__new__(cls, semantic)
        value.reference_id = reference_id
        return value

    def __reduce__(self):
        return self.__class__, (str(self), self.reference_id)


KNOWLEDGE_PERSISTENCE_INSTRUCTION_RE = re.compile(
    r"(?:\.work-bundle/knowledge(?:/|\b)|\bks-[a-z0-9-]+\b)",
    re.IGNORECASE,
)
FORBIDDEN_EXECUTOR_RESULT_FIELDS = {
    "suggested_durable_conclusions",
    "durable_candidate_facts",
    "recommended_orchestration_review",
    "recommended_next_actions",
    "delegation",
    "deviations",
    "strategy_advice",
    "knowledge_persistence",
    "baseline",
    "mutation_events",
    "accepted_dependency_deltas",
}
FORBIDDEN_CREATION_CONTROL_FIELDS = {
    "acceptance_review",
    "accepted_result",
    "accepted_result_id",
    "accepted_at",
    "accepted_observations",
    "reviewer",
    "verdict",
    "target_identity",
    "review_mode",
    "repair_frontier",
    "review_reset",
    "reviewer_run",
    "publication",
    "receipt",
}
VALID_RESULT_STATES = {"completed", "blocked", "partial", "failed"}
TASK_FIT_RESULTS = {"clean", "repaired", "unresolved", "skipped"}
EXECUTOR_CAPABILITIES = {"mechanical", "standard", "judgment"}
SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}

REQUIRED_EVALUATION_NEIGHBOR_FAMILIES = (
    "production composition",
    "identity replay",
    "owner state",
    "symlink containment",
    "effect boundary",
    "evidence provenance",
    "evaluator context",
)


def required_evaluation_neighbors() -> tuple[str, ...]:
    """Return the fixed REQ-064 risk-neighbor obligations in authority order."""
    return REQUIRED_EVALUATION_NEIGHBOR_FAMILIES


def _capability_index_module() -> Any:
    name = "_work_bundle_semantic_capability_index"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = Path(__file__).resolve().parents[1] / "keep-summarizing" / "capability_index.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Unable to load semantic capability runtime: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _trusted_capability_node(index: Any, node: Any) -> bool:
    authority = {
        item.evidence_id
        for item in index.evidence
        if item.authority is True
        or isinstance(item.authority, str)
        and item.authority.casefold() in {"authoritative", "accepted", "current", "confirmed"}
    }
    return (
        node.lifecycle in {"grounded", "accepted"}
        and node.freshness == "current"
        and bool(set(node.evidence_ids) & authority)
    )


def capability_authority_delta(before: Any, after: Any) -> dict[str, list[str]]:
    """Describe authority changes without promoting candidate or stale semantic data."""
    before_nodes = {node.node_id: node for node in before.nodes}
    after_nodes = {node.node_id: node for node in after.nodes}
    before_trusted = {key for key, node in before_nodes.items() if _trusted_capability_node(before, node)}
    after_trusted = {key for key, node in after_nodes.items() if _trusted_capability_node(after, node)}
    shared = before_trusted & after_trusted
    changed = sorted(
        node_id
        for node_id in shared
        if before_nodes[node_id].to_dict() != after_nodes[node_id].to_dict()
    )
    advisory_only = sorted(
        node_id
        for node_id in after_nodes.keys() - before_nodes.keys()
        if not _trusted_capability_node(after, after_nodes[node_id])
    )
    return {
        "added": sorted(after_trusted - before_trusted),
        "removed": sorted(before_trusted - after_trusted),
        "changed": changed,
        "advisory_only": advisory_only,
    }


def project_capability_neighborhood(
    index: Any,
    query_text: str,
    *,
    depth: str = "standard",
    max_nodes: int = 32,
) -> dict[str, Any]:
    """Project a bounded, provenance-bearing semantic neighborhood into executor context."""
    capability = _capability_index_module()
    if depth not in capability.TRAVERSAL_DEPTHS:
        raise SystemExit("Capability projection depth must be light, standard, or deep")
    if not isinstance(max_nodes, int) or isinstance(max_nodes, bool) or max_nodes < 1:
        raise SystemExit("Capability projection max_nodes must be a positive integer")
    ranked = capability.rank_candidates(index, query_text)
    chosen: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()
    gaps: list[str] = []
    obligations: list[dict[str, Any]] = []
    for family in required_evaluation_neighbors():
        matches = capability.rank_candidates(index, family)
        match = next((item for item in matches if item.trusted), None)
        if match is None:
            gaps.append(f"missing required evaluation neighbor: {family}")
            obligations.append({"obligation_id": f"neighbor:{family.replace(' ', '-')}", "kind": "evaluation_neighbor", "status": "blocked", "evidence_ids": []})
            continue
        obligations.append({"obligation_id": f"neighbor:{family.replace(' ', '-')}", "kind": "evaluation_neighbor", "status": "satisfied", "evidence_ids": list(index.node(match.node_id).evidence_ids)})
        if match.node_id not in seen:
            chosen.append((match.node_id, f"required_evaluation_neighbor:{family}", None))
            seen.add(match.node_id)
    for item in ranked:
        if item.trusted and item.node_id not in seen:
            chosen.append((item.node_id, "intent_match", None))
            seen.add(item.node_id)

    from dataclasses import replace
    trusted = {node.node_id for node in index.nodes if _trusted_capability_node(index, node)}
    graph = replace(index, nodes=tuple(node for node in index.nodes if node.node_id in trusted),
                    relations=tuple(edge for edge in index.relations
                                    if edge.from_id in trusted and edge.to_id in trusted))
    traversal = capability.traverse_capabilities(graph, list(seen), depth=depth, max_nodes=max_nodes) if seen else None
    if traversal:
        for entry in traversal.inclusions:
            if entry.node_id not in seen:
                chosen.append((entry.node_id, "typed_relation", None))
                seen.add(entry.node_id)
    included_candidates = chosen[:max_nodes]
    included_ids = {item[0] for item in included_candidates}
    frontier = sorted(({node_id for node_id, _, _ in chosen[max_nodes:]} |
                       set(traversal.frontier if traversal else ())) - included_ids)
    inclusions: list[dict[str, Any]] = []
    for rank, (node_id, reason, family) in enumerate(included_candidates, start=1):
        node = index.node(node_id)
        inclusion: dict[str, Any] = {
            "node_id": node_id, "reason": reason, "rank": rank,
            "evidence_ids": list(node.evidence_ids),
        }
        inclusions.append(inclusion)
    exclusions = []
    for node in sorted(index.nodes, key=lambda item: item.node_id):
        if _trusted_capability_node(index, node):
            continue
        reason = "stale" if node.freshness == "stale" else "non_authoritative"
        exclusions.append({"node_id": node.node_id, "reason": reason})
    query_tokens = {token.casefold() for token in re.findall(r"[A-Za-z0-9_]+", query_text)}
    trigger_map = {
        "permission": {"permission", "access"}, "ownership": {"owner", "ownership"},
        "destructive_effect": {"delete", "destructive", "remove"}, "data_effect": {"data", "database"},
        "external_effect": {"external", "remote", "network"}, "state_transition": {"state", "transition"},
        "compatibility": {"compatibility", "legacy"}, "evidence_conflict": {"conflict", "contradiction"},
    }
    triggers = [name for name, tokens in trigger_map.items() if query_tokens & tokens]
    source_payload = json.dumps(index.to_dict(), sort_keys=True, separators=(",", ":"))
    return {
        "query_id": f"query:{hashlib.sha256(query_text.encode('utf-8')).hexdigest()[:20]}",
        "query_text_digest": f"sha256:{hashlib.sha256(query_text.encode('utf-8')).hexdigest()}",
        "depth": depth,
        "obligations": obligations,
        "triggers": triggers,
        "inclusions": inclusions,
        "exclusions": exclusions,
        "frontier": [
            {"node_id": node_id, "information_value": 1.0, "evidence_cost": 1.0, "miss_risk": 1.0, "expand": True}
            for node_id in frontier
        ],
        "gaps": gaps,
        "stopping_reason": ("node_budget" if len(chosen) > max_nodes else
                            traversal.stopping_reason if traversal else "frontier_exhausted"),
        "source_index_digest": f"sha256:{hashlib.sha256(source_payload.encode('utf-8')).hexdigest()}",
    }


def _source_paths(values: Any) -> list[str]:
    return [
        str(value)
        for value in _as_list(values)
        if Path(str(value).split("#", 1)[0]).suffix.lower() in SOURCE_SUFFIXES
    ]


def task_evidence_applicability(task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the monotonic, reason-coded evidence requirements owned by a task."""

    reasons: dict[str, list[str]] = {"metadata": [], "repository": [], "codegraph": []}

    def require(kind: str, reason: str) -> None:
        if reason not in reasons[kind]:
            reasons[kind].append(reason)

    if task.get("project_metadata_required") is True or task.get("metadata_preflight"):
        require("metadata", "project-metadata-preflight")

    binding = task.get("execution_binding")
    if isinstance(binding, dict) and binding.get("target_kind") == "git-backed":
        require("repository", "repository-target-binding")
    if task.get("repository_id") or task.get("repository_target"):
        require("repository", "repository-target")
    if task.get("repository_preflight"):
        require("repository", "repository-preflight")
    if task.get("accepted_repository_baseline") or task.get("repository_baseline"):
        require("repository", "accepted-repository-baseline")
    if _as_list(task.get("changed_paths")):
        require("repository", "changed-paths")
    if task.get("repository_blocker_state"):
        require("repository", "repository-blocker-state")

    files = task.get("files") if isinstance(task.get("files"), dict) else {}
    read_paths = _source_paths([*_as_list(files.get("read")), *_as_list(task.get("source_files"))])
    write_paths = _source_paths([*_as_list(files.get("write")), *_as_list(task.get("target_files"))])
    source_reasons: list[str] = []
    if read_paths:
        source_reasons.append("source-inspection")
    if write_paths:
        source_reasons.append("source-editing")
    if _as_list(task.get("target_symbols")) or _as_list(task.get("dependency_paths")) or _as_list(
        task.get("call_chains")
    ):
        source_reasons.append("source-analysis")
    validation = [item for item in _as_list(task.get("validation")) if isinstance(item, dict)]
    if any(
        _source_paths(item.get("command"))
        or re.search(r"(?:^|\s)(?:pytest|unittest|cargo test|go test|pnpm test|npm test)(?:\s|$)", str(item.get("command") or ""))
        for item in validation
    ):
        source_reasons.append("source-validation")
    for reason in source_reasons:
        require("repository", reason)
        require("codegraph", reason)

    return {
        kind: {"required": bool(kind_reasons), "reasons": kind_reasons}
        for kind, kind_reasons in reasons.items()
    }


def _compile_executor_profile(task: dict[str, Any], task_path: Path) -> dict[str, Any]:
    if "executor_profile" not in task:
        return {"capability": "standard", "context_mode": "compiled-brief"}
    profile = task["executor_profile"]
    if not isinstance(profile, dict):
        raise SystemExit(f"Task executor_profile must be a mapping: {task_path}")
    capability = profile.get("capability")
    if capability not in EXECUTOR_CAPABILITIES:
        allowed = ", ".join(sorted(EXECUTOR_CAPABILITIES))
        raise SystemExit(f"Task executor_profile.capability must be one of {allowed}: {task_path}")
    return dict(profile)
















def _protected_project_path(raw: object, root: Path) -> bool:
    text = str(raw).strip()
    path = Path(text).expanduser()
    if path.is_absolute():
        try:
            text = path.resolve(strict=False).relative_to(root.resolve()).as_posix()
        except ValueError:
            return True
    text = text.removeprefix("./")
    return (
        text == "credentials"
        or text.startswith("credentials/")
        or text == ".work-bundle/knowledge"
        or text.startswith(".work-bundle/knowledge/")
    )


def _task_scope_paths(values: list[Any], root: Path, label: str) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        try:
            text = canonical_relative_path(text, allow_tree_pattern=label == "forbidden scope")
        except OwnershipBlocker as error:
            raise SystemExit(f"Task {label} contains an unsafe path: {value}") from error
        if label != "forbidden scope" and _protected_project_path(text, root):
            raise SystemExit(f"Task {label} uses a forbidden protected path: {text}")
        if label == "write scope" and _directory_or_module_write_path(text, root):
            raise SystemExit(f"Task write scope is a directory or module path and fails closed: {text}")
        result.append(text)
    return result


def _directory_or_module_write_path(text: str, root: Path) -> bool:
    candidate = root / text
    if text.endswith(("/", "\\")):
        return True
    if candidate.exists():
        return candidate.is_dir()
    dotted_module = "/" not in text and "\\" not in text and "." in text and not text.startswith(".")
    if dotted_module and Path(text).suffix not in {".py", ".md", ".ts", ".js", ".yaml", ".yml", ".json"}:
        return True
    return False


def _artifact_id(data: dict[str, Any], key: str, path: Path) -> str:
    value = str(data.get(key, "")).strip()
    if not value or not SAFE_ID_RE.fullmatch(value):
        raise SystemExit(f"Missing or unsafe {key} in {path}")
    return value


def _find_plan(root: Path, plan_id: str) -> tuple[Path, dict[str, Any]]:
    plan_root = root / ".work-bundle/orchestration/plan"
    matches: list[tuple[Path, dict[str, Any]]] = []
    policy = family_policy(load_catalog(PLAN_CATALOG), "root-plan")
    anchors = {"workspace_root": root}
    for state in ("active", "archived"):
        candidate = canonical_artifact_path(
            policy, anchors, identity=plan_id, state=state
        )
        if not candidate.is_file():
            continue
        raw = read_yaml_mapping(candidate)
        source_spec_id = str(raw.get("source_spec_id") or "")
        result = read_artifact(
            PLAN_CATALOG, "root-plan", anchors, identity=plan_id, state=state,
            bindings={"source_spec": source_spec_id},
        )
        matches.append((candidate, dict(result["data"])))
    if len(matches) != 1:
        raise SystemExit(f"Expected one root plan for {plan_id}; found {len(matches)} under {plan_root}")
    return matches[0]




def _assert_no_credential_values(value: Any, context: str = "packet") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SENSITIVE_KEY_RE.search(str(key)) and child not in (None, "", [], {}):
                raise SystemExit(f"Blocked credential-like value in {context}")
            _assert_no_credential_values(child, context)
    elif isinstance(value, list):
        for child in value:
            _assert_no_credential_values(child, context)
    elif isinstance(value, str) and SENSITIVE_ASSIGNMENT_RE.search(value):
        raise SystemExit(f"Blocked credential-like value in {context}")


def _assert_not_excellence_proposal_id(identifier: str, context: str) -> None:
    if EXCELLENCE_PROPOSAL_RE.fullmatch(identifier):
        raise SystemExit(
            f"Non-authoritative source ID {identifier}: excellence proposal IDs are excluded from {context}"
        )


def _resolve_reference(value: Any, records: dict[str, str], source_paths: list[Path]) -> Any:
    if isinstance(value, str) and SOURCE_ID_RE.fullmatch(value):
        _assert_not_excellence_proposal_id(value, "compiled briefs")
        if value not in records:
            sources = ", ".join(path.as_posix() for path in source_paths)
            raise SystemExit(f"Unresolved source ID {value}; searched: {sources}")
        return f"{value}: {records[value]}"
    if isinstance(value, list):
        return [_resolve_reference(item, records, source_paths) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_reference(item, records, source_paths) for key, item in value.items()}
    return value


def _nonempty_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
















def _source_knowledge_entry(entry: Any) -> tuple[str | None, str | None]:
    if isinstance(entry, str):
        return _nonempty_text(entry), None
    if isinstance(entry, dict):
        return _nonempty_text(entry.get("path")), _nonempty_text(entry.get("constraint"))
    return None, None


def _constraint_exposes_knowledge_path(constraint: str) -> bool:
    normalized = constraint.strip().removeprefix("./")
    return (
        normalized == ".work-bundle/knowledge"
        or normalized.startswith(".work-bundle/knowledge/")
        or ".work-bundle/knowledge/" in normalized
    )


def _verified_specification_authority(source_paths: list[Path]) -> dict[str, str]:
    accepted: dict[str, str] = {}
    authority_index = 0
    for source_path in source_paths:
        metadata, _ = _read_structured(source_path)
        if metadata.get("status") != "verified":
            raise SystemExit(f"Task decision_authority requires a verified specification: {source_path}")
        for entry in _as_list(metadata.get("source_knowledge")):
            path, constraint = _source_knowledge_entry(entry)
            if path is None and constraint is None:
                continue
            authority_index += 1
            accepted[f"AUTH-{authority_index:03d}"] = constraint or ""
    return accepted


def read_structured_artifact(path: Path) -> dict[str, Any]:
    data, _ = _read_structured(path)
    return data


def _compile_truth_basis(
    task: dict[str, Any],
    records: dict[str, str],
    source_paths: list[Path],
) -> dict[str, Any]:
    raw = task.get("truth_basis")
    if not isinstance(raw, dict):
        raise SystemExit("Task Truth Basis is required")
    missing = [field for field in TRUTH_BASIS_FIELDS if field not in raw]
    if missing:
        raise SystemExit(f"Task Truth Basis missing fields: {', '.join(missing)}")
    purpose = raw.get("purpose")
    if not isinstance(purpose, str) or not purpose.strip():
        raise SystemExit("Task Truth Basis purpose must be non-empty")
    list_fields: dict[str, list[Any]] = {}
    for field in ("as_is_evidence", "decision_authority", "expected_delta"):
        values = _as_list(raw.get(field))
        if not values or any(not isinstance(value, str) or not value.strip() for value in values):
            raise SystemExit(f"Task Truth Basis {field} must be a non-empty string list")
        list_fields[field] = values
    decision_authority = list_fields["decision_authority"]
    accepted_authority = _verified_specification_authority(source_paths)
    if decision_authority == ["none-relevant"]:
        compiled_authority = decision_authority
    else:
        compiled_authority = []
        if "none-relevant" in decision_authority:
            raise SystemExit(
                "Task Truth Basis decision_authority must use none-relevant or verified specification authority"
            )
        for value in decision_authority:
            if value not in accepted_authority:
                raise SystemExit(
                    "Task Truth Basis decision_authority must use none-relevant or verified specification authority"
                )
            constraint = accepted_authority[value]
            if not constraint:
                raise SystemExit(
                    f"Task Truth Basis {value} is missing a carried semantic constraint from verified specification source_knowledge"
                )
            if _constraint_exposes_knowledge_path(constraint):
                raise SystemExit(
                    f"Task Truth Basis {value} carried constraint must not expose a knowledge path"
                )
            compiled_authority.append(f"{value}: {constraint}")
    conflict_status = raw.get("conflict_status")
    if conflict_status not in {"clear", "escalate"}:
        raise SystemExit("Task Truth Basis conflict_status must be clear or escalate")
    if conflict_status == "escalate":
        raise SystemExit("decision-blocked: Task Truth Basis conflict requires authority repair")
    return {
        "purpose": purpose.strip(),
        "as_is_evidence": _resolve_reference(list_fields["as_is_evidence"], records, source_paths),
        "decision_authority": compiled_authority,
        # Source meanings are projected once elsewhere; the Truth Basis carries
        # their stable IDs rather than duplicating accepted prose.
        "expected_delta": _retain_source_references(list_fields["expected_delta"], records),
        "conflict_status": conflict_status,
    }


def _retain_source_references(value: Any, records: dict[str, str]) -> Any:
    if isinstance(value, str) and value in records:
        return value
    if isinstance(value, list):
        return [_retain_source_references(item, records) for item in value]
    if isinstance(value, dict):
        return {key: _retain_source_references(item, records) for key, item in value.items()}
    return value


def _compile_validation_references(value: Any, records: dict[str, str]) -> Any:
    if isinstance(value, str) and value in records:
        return _SemanticReference(f"{value}: {records[value]}", value)
    if isinstance(value, list):
        return [_compile_validation_references(item, records) for item in value]
    if isinstance(value, dict):
        return {key: _compile_validation_references(item, records) for key, item in value.items()}
    return value


def semantic_digest(value: Any) -> str:
    """Return a stable digest for projected semantic or evidence identity."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _compile_semantic_authority(
    source_ids: list[str],
    records: dict[str, str],
    truth_basis: dict[str, Any],
) -> dict[str, Any]:
    """Index each accepted meaning at its single canonical packet location."""

    index: dict[str, dict[str, str]] = {}
    interface_semantics: dict[str, str] = {}
    validation_semantics: dict[str, str] = {}
    for source_id in source_ids:
        if source_id.startswith("CON-"):
            field = "constraints"
        elif source_id.startswith(("API-", "IFACE-")):
            field = "interface_semantics"
            interface_semantics[source_id] = f"{source_id}: {records[source_id]}"
        elif source_id.startswith("TEST-"):
            field = "validation_semantics"
            validation_semantics[source_id] = f"{source_id}: {records[source_id]}"
        else:
            field = "requirements"
        index[source_id] = {
            "canonical_field": field,
            "digest": semantic_digest(records[source_id]),
        }
    for authority in _as_list(truth_basis.get("decision_authority")):
        alias = str(authority).split(":", 1)[0].strip()
        if AUTH_ALIAS_RE.fullmatch(alias):
            index[alias] = {
                "canonical_field": "truth_basis.decision_authority",
                "digest": semantic_digest(authority),
            }
    return {
        "records": index,
        "interface_semantics": interface_semantics,
        "validation_semantics": validation_semantics,
    }


def _compile_capability_projection(
    executor_profile: dict[str, Any], rules: list[dict[str, Any]], skill_names: list[Any]
) -> dict[str, Any]:
    return {
        "executor": {
            "capability": executor_profile["capability"],
            "reason": "task executor_profile allocation",
        },
        "rules": [
            {"id": str(item["id"]), "reason": str(item["requirement"])}
            for item in rules
        ],
        "skills": [
            {"id": str(name), "reason": "task methodology allocation"}
            for name in skill_names
        ],
        "traversal": "runtime_only",
    }


def _encoded_bytes(value: Any) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def compiled_context_metrics(
    task_brief: dict[str, Any],
    *,
    evidence_projection: list[dict[str, Any]] | None = None,
    omitted_by_reference_bytes: int = 0,
    expansion_reason: str | None = None,
) -> dict[str, Any]:
    """Measure a compiled packet without imposing a global size policy."""

    if expansion_reason not in CONTEXT_EXPANSION_REASONS:
        raise SystemExit("compiled context expansion_reason is invalid")
    semantic_projection = {
        "semantic_authority": task_brief.get("semantic_authority", {}),
        "requirements": task_brief.get("requirements", []),
        "constraints": task_brief.get("constraints", []),
        "decision_authority": (task_brief.get("truth_basis") or {}).get("decision_authority", []),
    }
    return {
        "task_brief_bytes": len(("\n".join(_dump_yaml({"task_brief": task_brief})) + "\n").encode("utf-8")),
        "semantic_authority_bytes": _encoded_bytes(semantic_projection),
        "allocated_rule_bytes": _encoded_bytes(task_brief.get("allocated_rules", [])),
        "allocated_skill_bytes": _encoded_bytes((task_brief.get("methodology") or {}).get("skills", [])),
        "capability_projection_bytes": _encoded_bytes(task_brief.get("capability_projection", {})),
        "evidence_projection_bytes": _encoded_bytes(
            evidence_projection if evidence_projection is not None else task_brief.get("evidence_capability", {})
        ),
        "omitted_by_reference_bytes": max(0, int(omitted_by_reference_bytes)),
        "expansion_reason": expansion_reason,
    }




def _compile_evidence_capability(
    task: dict[str, Any], task_id: str, source_ids: list[str], validation: list[dict[str, Any]]
) -> dict[str, Any] | None:
    raw = task.get("evidence_capability")
    if raw is None:
        raise SystemExit("Task evidence_capability is required")
    if not isinstance(raw, dict) or raw.get("result") not in EVIDENCE_CAPABILITY_RESULTS:
        raise SystemExit("Task evidence_capability result must be mapped or no_validation_bearing_obligation")
    reason = _nonempty_text(raw.get("reason"))
    if reason is None:
        raise SystemExit("Task evidence_capability reason must be non-empty")
    invariants = [item for item in _as_list(raw.get("invariants")) if isinstance(item, dict)]
    if raw["result"] == "no_validation_bearing_obligation":
        if invariants:
            raise SystemExit("no_validation_bearing_obligation requires an empty invariant map")
        return {"result": raw["result"], "reason": reason, "invariants": []}
    if not invariants:
        raise SystemExit("mapped evidence_capability requires at least one invariant")
    validation_by_id = {str(item.get("id")): item for item in validation if _nonempty_text(item.get("id"))}
    compiled: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in invariants:
        invariant_id = _nonempty_text(item.get("id"))
        if invariant_id is None or invariant_id in seen:
            raise SystemExit("Evidence capability invariant IDs must be stable and unique")
        seen.add(invariant_id)
        allocated_sources = [str(value) for value in _as_list(item.get("source_ids"))]
        if not allocated_sources or any(value not in source_ids for value in allocated_sources):
            raise SystemExit(f"Evidence capability {invariant_id} cites unallocated source IDs")
        if item.get("boundary") not in EVIDENCE_BOUNDARIES:
            raise SystemExit(f"Evidence capability {invariant_id} has an invalid boundary")
        if item.get("boundary") == "other" and _nonempty_text(item.get("other_mechanism")) is None:
            raise SystemExit(f"Evidence capability {invariant_id} other boundary requires other_mechanism")
        if item.get("task_id") != task_id:
            raise SystemExit(f"Evidence capability {invariant_id} has the wrong task owner")
        evidence_ids = [str(value) for value in _as_list(item.get("evidence_ids"))]
        if not evidence_ids or any(value not in validation_by_id for value in evidence_ids):
            raise SystemExit(f"Evidence capability {invariant_id} cites missing validation evidence")
        for field in ("invariant", "oracle", "capability_reason", "freshness"):
            if _nonempty_text(item.get(field)) is None:
                raise SystemExit(f"Evidence capability {invariant_id} missing {field}")
        if str(item.get("oracle")) not in evidence_ids:
            raise SystemExit(f"Evidence capability {invariant_id} oracle must name an allocated evidence ID")
        if item.get("closure_result") != "pending":
            raise SystemExit(f"Evidence capability {invariant_id} closure_result must be initialized to pending")
        for evidence_id in evidence_ids:
            if invariant_id not in _as_list(validation_by_id[evidence_id].get("invariant_ids")):
                raise SystemExit(f"Validation {evidence_id} does not bind {invariant_id}")
            if _nonempty_text(validation_by_id[evidence_id].get("capability_reason")) is None:
                raise SystemExit(f"Validation {evidence_id} missing capability_reason")
        compiled.append(dict(item))
    return {"result": "mapped", "reason": reason, "invariants": compiled}








_EW_MODULE = None
_CP_MODULE = None


def _execution_workspace_module():
    global _EW_MODULE
    if _EW_MODULE is None:
        path = Path(__file__).resolve().parents[1] / "work-bundle" / "execution_workspace.py"
        helper_dir = str(path.parent)
        if helper_dir not in sys.path:
            sys.path.append(helper_dir)
        spec = importlib.util.spec_from_file_location("_wb_execution_workspace", path)
        if spec is None or spec.loader is None:
            raise SystemExit("Execution workspace helper is unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _EW_MODULE = module
    return _EW_MODULE


def _completion_provenance_module():
    global _CP_MODULE
    if _CP_MODULE is None:
        import completion_provenance

        _CP_MODULE = completion_provenance
    return _CP_MODULE


def _binding_path(control_root: Path, plan_id: str, task_id: str) -> Path:
    return control_root / ".work-bundle/runtime/execution" / plan_id / task_id / "execution-binding.json"


def _write_binding(path: Path, binding: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _persist_binding(binding: dict[str, Any], control_root: Path) -> None:
    _write_binding(_binding_path(control_root, str(binding["plan_id"]), str(binding["task_id"])), binding)


def _read_binding_file(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise SystemExit("Task execution binding is missing harness provenance")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("Task execution binding provenance is invalid") from error
    if not isinstance(document, dict):
        raise SystemExit("Task execution binding provenance is invalid")
    return document


def _iter_task_bindings(control_root: Path) -> list[dict[str, Any]]:
    root = control_root / ".work-bundle/runtime/execution"
    if not root.is_dir():
        return []
    bindings: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/*/execution-binding.json")):
        if path.is_file() and not path.is_symlink():
            bindings.append(_read_binding_file(path))
    return bindings


def _assert_no_overlapping_mutating_siblings(control_root: Path, binding: dict[str, Any]) -> None:
    execution_path = Path(str(binding.get("execution_path") or "")).resolve()
    for other in _iter_task_bindings(control_root):
        if other.get("plan_id") == binding.get("plan_id") and other.get("task_id") == binding.get("task_id"):
            continue
        if other.get("plan_id") != binding.get("plan_id"):
            continue
        other_path = Path(str(other.get("execution_path") or "")).resolve()
        if other_path != execution_path:
            continue
        if other.get("mutating") is True:
            raise SystemExit(
                "workspace-blocked: mutating sibling tasks on the same execution path must isolate via prepare_worktree or serialize"
            )


def _verify_binding_provenance(binding: dict[str, Any]) -> dict[str, Any]:
    ew = _execution_workspace_module()
    runtime_root = Path(str(binding.get("runtime_root") or ""))
    try:
        loaded = ew.load_state(
            runtime_root,
            str(binding.get("workspace_id") or ""),
            str(binding.get("execution_id") or ""),
            str(binding.get("repository_id") or ""),
        )
        status = ew.workspace_status(
            runtime_root,
            str(binding.get("workspace_id") or ""),
            str(binding.get("execution_id") or ""),
            str(binding.get("repository_id") or ""),
        )
    except ew.ExecutionWorkspaceError as error:
        raise SystemExit(f"Task execution binding provenance is stale: {error.code}") from error
    if status.get("status") != "active":
        raise SystemExit("Task execution binding provenance is stale or mismatched")
    state = loaded.get("execution_workspace_state") if isinstance(loaded.get("execution_workspace_state"), dict) else {}
    identity = loaded.get("git_identity") if isinstance(loaded.get("git_identity"), dict) else {}
    expected_path = Path(str(binding.get("execution_path") or "")).resolve()
    actual_path = Path(str(state.get("path") or "")).resolve()
    if expected_path != actual_path:
        raise SystemExit("Task execution binding path does not match execution-workspace provenance")
    stored_identity = binding.get("git_identity") if isinstance(binding.get("git_identity"), dict) else {}
    for key in ("source_repository", "git_common_dir", "git_dir", "branch_ref"):
        if stored_identity.get(key) != identity.get(key):
            raise SystemExit("Task execution binding Git provenance mismatch")
    return loaded


def create_or_load_task_execution_binding(
    *,
    control_root: Path,
    plan_id: str,
    task_id: str,
    workspace_id: str,
    execution_id: str,
    repository_id: str,
    runtime_root: Path,
    write_scope: list[str] | None = None,
    forbidden_scope: list[str] | None = None,
) -> dict[str, Any]:
    control_root = control_root.expanduser().resolve()
    runtime_root = runtime_root.expanduser().resolve()
    try:
        canonical_write_scope = [canonical_relative_path(path) for path in (write_scope or [])]
        canonical_forbidden_scope = [
            canonical_relative_path(path, allow_tree_pattern=True)
            for path in (forbidden_scope or [])
        ]
    except OwnershipBlocker as error:
        raise SystemExit(f"Task execution binding scope is unsafe: {error.reason}") from error
    plan_path, _ = _find_plan(control_root, plan_id)
    plan = read_structured_artifact(plan_path)
    if str(plan.get("status") or "").lower() != "verified":
        raise SystemExit("Task execution binding requires a verified canonical plan")
    if (control_root / ".work-bundle/project.yaml").is_file():
        from repository_preflight import resolve_target_repositories

        task_paths = list((plan_path.parent / plan_id).glob(f"*/{task_id}.task.yaml"))
        if len(task_paths) != 1:
            raise SystemExit("Task execution binding requires one canonical task")
        task = read_yaml_mapping(task_paths[0])
        if task.get("id") != task_id or task.get("plan_id") != plan_id or task.get("phase_id") != task_paths[0].parent.name:
            raise SystemExit("Task execution binding canonical task identity mismatch")
        files = task.get("files") if isinstance(task.get("files"), dict) else {}
        if not (_as_list(files.get("write")) or _as_list(task.get("target_files"))):
            raise SystemExit("Task execution binding requires a canonical write target")
        targets = resolve_target_repositories(control_root, task_files=[task_paths[0]])
        write_members = {
            str(row["metadata"]["id"])
            for row in targets
            if row["source"] == "task-write-scope" and isinstance(row.get("metadata"), dict)
        }
        if write_members != {repository_id}:
            raise SystemExit("Task execution binding repository mismatch with canonical write target")
    path = _binding_path(control_root, plan_id, task_id)
    if path.exists():
        binding = load_task_execution_binding(control_root, plan_id, task_id)
        for field, value in (
            ("workspace_id", workspace_id),
            ("execution_id", execution_id),
            ("repository_id", repository_id),
        ):
            if str(binding.get(field) or "") != str(value):
                raise SystemExit(f"Task execution binding {field} mismatch")
        if Path(str(binding.get("runtime_root") or "")).resolve() != runtime_root:
            raise SystemExit("Task execution binding runtime root mismatch")
        _verify_binding_provenance(binding)
        return binding
    loaded = _execution_workspace_module().load_state(runtime_root, workspace_id, execution_id, repository_id)
    state = loaded["execution_workspace_state"]
    identity = loaded["git_identity"]
    target_kind = "isolated_worktree" if state.get("kind") == "worktree" else "git_backed"
    ownership = _completion_provenance_module().execution_binding_ownership(
        control_root / ".work-bundle/runtime/completion-provenance",
        binding_id=f"binding:{plan_id}:{task_id}",
        target_kind=target_kind,
        owner=task_id,
    )
    binding = {
        "plan_id": plan_id,
        "task_id": task_id,
        "control_root": str(control_root),
        "workspace_id": workspace_id,
        "execution_id": execution_id,
        "repository_id": repository_id,
        "runtime_root": str(runtime_root),
        "execution_path": str(Path(str(state["path"])).resolve()),
        "state_path": loaded["state_path"],
        "git_identity": identity,
        "write_scope": canonical_write_scope,
        "forbidden_scope": canonical_forbidden_scope,
        "ownership": ownership,
        "mutating": True,
        "baseline": None,
    }
    _assert_no_overlapping_mutating_siblings(control_root, binding)
    _persist_binding(binding, control_root)
    return binding


def load_task_execution_binding(control_root: Path, plan_id: str, task_id: str) -> dict[str, Any]:
    binding = _read_binding_file(_binding_path(control_root.expanduser().resolve(), plan_id, task_id))
    if "ownership" not in binding:
        raise SystemExit("Task execution binding ownership is invalid")
    required = {
        "plan_id",
        "task_id",
        "workspace_id",
        "execution_id",
        "repository_id",
        "runtime_root",
        "execution_path",
        "state_path",
        "git_identity",
        "ownership",
    }
    if not required.issubset(binding):
        raise SystemExit("Task execution binding provenance is invalid")
    if binding.get("plan_id") != plan_id or binding.get("task_id") != task_id:
        raise SystemExit("Task execution binding identity mismatch")
    try:
        ownership = _completion_provenance_module().validate_execution_binding_ownership(
            control_root.expanduser().resolve() / ".work-bundle/runtime/completion-provenance",
            binding["ownership"],
        )
    except (KeyError, TypeError, _completion_provenance_module().CompletionProvenanceError) as error:
        raise SystemExit("Task execution binding ownership is invalid") from error
    if ownership.get("binding_id") != f"binding:{plan_id}:{task_id}":
        raise SystemExit("Task execution binding ownership identity mismatch")
    _verify_binding_provenance(binding)
    return binding














def capture_task_baseline_once(binding: dict[str, Any], control_root: Path | None = None) -> dict[str, Any]:
    existing = binding.get("baseline")
    if isinstance(existing, dict) and existing.get("head"):
        return binding
    try:
        evidence = capture_repository_evidence(Path(str(binding["execution_path"])))
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    updated = dict(binding)
    updated["baseline"] = evidence
    root = control_root or Path(str(binding.get("control_root") or ""))
    if not root.is_dir():
        raise SystemExit("Task execution binding control root is required to persist baseline")
    _persist_binding(updated, root)
    return updated

































def _yaml_scalar(value: Any) -> str:
    if isinstance(value, _SemanticReference):
        return value.reference_id
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_./*:-]+", text) and ": " not in text:
        return text
    return json.dumps(text, ensure_ascii=False)


def _dump_yaml(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                if not child:
                    lines.append(f"{prefix}{key}: {'[]' if isinstance(child, list) else '{}'}")
                else:
                    lines.append(f"{prefix}{key}:")
                    lines.extend(_dump_yaml(child, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(child)}")
        return lines
    if isinstance(value, list):
        lines = []
        for child in value:
            if isinstance(child, dict):
                if not child:
                    lines.append(f"{prefix}- {{}}")
                    continue
                items = list(child.items())
                key, first = items[0]
                if isinstance(first, (dict, list)):
                    lines.append(f"{prefix}- {key}:")
                    lines.extend(_dump_yaml(first, indent + 4))
                else:
                    lines.append(f"{prefix}- {key}: {_yaml_scalar(first)}")
                for key, item in items[1:]:
                    if isinstance(item, (dict, list)):
                        lines.append(f"{prefix}  {key}:")
                        lines.extend(_dump_yaml(item, indent + 4))
                    else:
                        lines.append(f"{prefix}  {key}: {_yaml_scalar(item)}")
            else:
                lines.append(f"{prefix}- {_yaml_scalar(child)}")
        return lines
    return [f"{prefix}{_yaml_scalar(value)}"]


VALIDATION_KINDS = {"process", "inspection"}


def _compile_structured_validation_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise SystemExit("Task validation items must be mappings")
    compiled: dict[str, Any] = {}
    kind = str(item.get("kind") or "").strip().lower()
    if kind not in VALIDATION_KINDS:
        raise SystemExit(
            "Task validation kind must be process or inspection; untyped structured validation is legacy-untyped"
        )
    compiled["kind"] = kind
    if "reuse_seconds" in item or "evidence_reuse" in item:
        try:
            compiled["evidence_reuse"] = _completion_provenance_module().validation_reuse_policy(item)
        except ValueError as error:
            raise SystemExit(str(error)) from error
    for key in ("id", "invariant_ids", "capability_reason", "command", "proves", "expected", "acceptable_results", "digest"):
        if key in item:
            compiled[key] = item[key]
    if kind == "inspection":
        mechanism = str(item.get("mechanism") or "").strip()
        if not mechanism:
            raise SystemExit("Inspection validation requires a named harness-owned mechanism")
        compiled["mechanism"] = mechanism
    return compiled


def _compile_task_validation(task: dict[str, Any]) -> list[Any]:
    validation_items = _as_list(task.get("validation"))
    if validation_items:
        task_policy = task.get("evidence_reuse")
        compiled: list[dict[str, Any]] = []
        for item in validation_items:
            if task_policy is not None and isinstance(item, dict) and not (
                "evidence_reuse" in item or "reuse_seconds" in item
            ):
                item = {**item, "evidence_reuse": task_policy}
            elif task_policy is not None and not isinstance(item, dict):
                raise SystemExit("Task validation items must be mappings")
            compiled.append(_compile_structured_validation_item(item))
        return compiled
    raise SystemExit(
        "Task validation must declare structured items with explicit kind"
    )


def _task_context(
    args: argparse.Namespace,
    *,
    task_override: dict[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any], dict[str, str], list[Path]]:
    explicit_root = getattr(args, "_resolved_root", None)
    root = Path(str(explicit_root)).resolve() if explicit_root else resolve_workspace_root(args)
    task_root = root / ".work-bundle/orchestration/plan"
    task_path = _input_path(args.task, root, task_root, "task")
    stored_task_data, _ = _read_structured(task_path)
    task_id = _artifact_id(stored_task_data, "id", task_path)
    plan_id = _artifact_id(stored_task_data, "plan_id", task_path)
    phase_id = _artifact_id(stored_task_data, "phase_id", task_path)
    plan_path, plan_data = _find_plan(root, plan_id)
    state = plan_path.relative_to(task_root).parts[0]
    task_result = read_artifact(
        PLAN_CATALOG, "task", {"workspace_root": root}, identity=task_id,
        state=state, bindings={"plan": plan_id, "phase": phase_id},
    )
    if Path(str(task_result["path"])).resolve() != task_path.resolve():
        raise SystemExit(f"Task is not at its canonical location: {task_path}")
    task_data = dict(task_override) if task_override is not None else stored_task_data
    for field, expected in (("id", task_id), ("plan_id", plan_id), ("phase_id", phase_id)):
        if str(task_data.get(field) or "") != expected:
            raise SystemExit(f"Task candidate changes canonical {field}: {task_path}")
    read_artifact(
        PLAN_CATALOG, "phase", {"workspace_root": root}, identity=phase_id,
        state=state, bindings={"plan": plan_id},
    )
    source_paths = _resolve_spec_paths(root, task_data, plan_data)
    records = source_obligation_records(task_data, label="Canonical task")
    for source_path in source_paths:
        source_data, _body = _read_structured(source_path)
        if source_path.parent.name != "active" or source_data.get("status") != "verified":
            raise SystemExit(
                f"Task source specification must be canonical, active, and verified: {source_path}"
            )
    return root, task_path, task_data, records, source_paths


def _contains_resolved_source_record(value: Any, record: str) -> bool:
    if isinstance(value, str):
        return record in value
    if isinstance(value, dict):
        return any(_contains_resolved_source_record(item, record) for item in value.values())
    if isinstance(value, list):
        return any(_contains_resolved_source_record(item, record) for item in value)
    return False


STATIC_TASK_FIELDS = frozenset(
    {
        "id",
        "artifact_type",
        "schema_version",
        "plan_id",
        "phase_id",
        "name",
        "goal",
        "status",
        "order",
        "task_type",
        "date_created",
        "last_updated",
        "updated_at",
        "owner",
        "depends_on",
        "source_ids",
        "source_obligations",
        "truth_basis",
        "source_files",
        "target_files",
        "forbidden_files",
        "target_symbols",
        "interfaces",
        "steps",
        "completion_criteria",
        "methodology",
        "executor_profile",
        "acceptance_review",
        "allocated_rules",
        "allocated_skills",
        "validation",
        "evidence_reuse",
        "evidence_capability",
        "files",
        "project_metadata_required",
        "metadata_preflight",
        "repository_id",
        "repository_target",
        "repository_preflight",
        "accepted_repository_baseline",
        "repository_baseline",
        "dependency_paths",
        "call_chains",
        "path",
        "accepted_result",
        "accepted_results",
        "accepted_result_reference",
        "accepted_result_references",
        "evidence_reference",
        "evidence_references",
        "handoff_contract",
    }
)


def _assert_static_task_fields(task: dict[str, Any], task_path: Path) -> None:
    unsupported = sorted(set(task) - STATIC_TASK_FIELDS)
    if unsupported:
        raise SystemExit(
            f"Task has unsupported static contract fields {', '.join(unsupported)}: {task_path}"
        )


def _is_proven_historical_cleanup_target(
    task: dict[str, Any],
    path: str,
    cleanup_baselines: Mapping[Path, str],
    planning_sources: Iterable[Path],
) -> bool:
    truth_basis = task.get("truth_basis") if isinstance(task.get("truth_basis"), dict) else {}
    purpose = str(truth_basis.get("purpose") or "").lower()
    criteria = " ".join(str(value).lower() for value in _as_list(task.get("completion_criteria")))
    if "remove" not in purpose or "absent from source" not in criteria:
        return False
    if not cleanup_baselines:
        for source_member in planning_sources:
            at_plan_head = subprocess.run(
                ["git", "-C", str(source_member), "cat-file", "-e", f"HEAD:{path}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if at_plan_head.returncode == 0 and os.path.lexists(source_member / path):
                return True
        return False
    for source_member, baseline in cleanup_baselines.items():
        at_baseline = subprocess.run(
            ["git", "-C", str(source_member), "cat-file", "-e", f"{baseline}:{path}"],
            capture_output=True,
            text=True,
            check=False,
        )
        at_result = subprocess.run(
            ["git", "-C", str(source_member), "cat-file", "-e", f"HEAD:{path}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if at_baseline.returncode == 0 and at_result.returncode != 0 and not os.path.lexists(
            source_member / path
        ):
            return True
    return False


def _assert_no_source_local_execution_artifacts(
    task: dict[str, Any],
    task_path: Path,
    *,
    cleanup_baselines: Mapping[Path, str] | None = None,
    planning_sources: Iterable[Path] = (),
) -> None:
    files = task.get("files") if isinstance(task.get("files"), dict) else {}
    write_paths = _as_list(files.get("write")) or _as_list(task.get("target_files"))
    for value in write_paths:
        try:
            path = canonical_relative_path(str(value))
        except OwnershipBlocker:
            continue
        parts = Path(path).parts
        issue_eval = (
            len(parts) >= 2
            and parts[0] == "evals"
            and re.fullmatch(r"(?:wor|issue)[-_]?\d+", parts[1], re.IGNORECASE)
        )
        issue_test = (
            len(parts) == 2
            and parts[0] == "tests"
            and re.match(r"test_(?:wor|issue)[-_]?\d+(?:_|\.py)", parts[1], re.IGNORECASE)
        )
        workspace_execution = path == "orchestration/executions" or path.startswith(
            "orchestration/executions/"
        )
        historical_cleanup = (issue_eval or issue_test) and _is_proven_historical_cleanup_target(
            task, path, cleanup_baselines or {}, planning_sources
        )
        if workspace_execution or ((issue_eval or issue_test) and not historical_cleanup):
            raise SystemExit(
                f"Task write scope uses a source-local execution artifact path: {task_path}: {path}"
            )


def compile_task_authority(root: Path, task_path: Path) -> dict[str, Any]:
    """Compile current task authority without materializing runtime artifacts."""

    compile_args = argparse.Namespace(
        workspace_root=str(root),
        task=str(task_path),
        handoff=None,
        base=None,
        head=None,
    )
    return _compile_task_brief(compile_args)[1]["task_brief"]


def static_task_brief(root: Path, task_path: Path) -> dict[str, Any]:
    """Compile one task's static authority without runtime bindings or dependency results."""

    task, _ = _read_structured(task_path)
    _assert_static_task_fields(task, task_path)
    cleanup_baselines: dict[Path, str] = {}
    task_plan_id = str(task.get("plan_id") or "")
    task_id = str(task.get("id") or "")
    binding_path = _binding_path(root, task_plan_id, task_id)
    if binding_path.is_file():
        binding = load_task_execution_binding(root, task_plan_id, task_id)
        baseline = binding.get("baseline") if isinstance(binding.get("baseline"), dict) else {}
        execution_path = str(binding.get("execution_path") or "")
        baseline_head = str(baseline.get("head") or "")
        if (
            binding.get("plan_id") == task.get("plan_id")
            and binding.get("task_id") == task.get("id")
            and execution_path
            and baseline_head
        ):
            cleanup_baselines[Path(execution_path).expanduser().resolve()] = baseline_head
    planning_sources = _member_roots(root) if (root / ".work-bundle/project.yaml").is_file() else []
    if not planning_sources and (root / ".git").exists():
        planning_sources = [root]
    _assert_no_source_local_execution_artifacts(
        task,
        task_path,
        cleanup_baselines=cleanup_baselines,
        planning_sources=planning_sources,
    )
    return compile_task_authority(root, task_path)


def static_plan_task_admission(
    root: Path, plan_path: Path, *, content: str | None = None
) -> list[dict[str, Any]]:
    """Compile and statically admit every task belonging to one executable plan."""

    plan_root = root / ".work-bundle/orchestration/plan"
    if not plan_path.resolve().is_relative_to(plan_root.resolve()):
        raise SystemExit("plan review static-admission-blocked: root plan escapes plan store")
    if content is not None:
        raise SystemExit(
            "plan review static-admission-blocked: in-memory plan content is not canonical stored authority"
        )
    plan, _ = _read_structured(plan_path)
    plan_id = _artifact_id(plan, "id", plan_path)
    canonical_plan_path, _canonical_plan = _find_plan(root, plan_id)
    if canonical_plan_path.resolve() != plan_path.resolve():
        raise SystemExit("plan review static-admission-blocked: root plan is not canonical")
    state = canonical_plan_path.relative_to(plan_root).parts[0]
    phase_index = rebuild_index(
        PLAN_CATALOG, "phase", {"workspace_root": root}
    )
    phase_rows = [
        json.loads(line)
        for line in Path(str(phase_index["path"])).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    phase_rows = [row for row in phase_rows if str(row.get("plan_id") or "") == plan_id]
    phase_data: dict[str, dict[str, Any]] = {}
    for row in phase_rows:
        phase_id = str(row["id"])
        stored = read_artifact(
            PLAN_CATALOG, "phase", {"workspace_root": root}, identity=phase_id,
            state=state, bindings={"plan": plan_id},
        )
        phase_data[phase_id] = dict(stored["data"])
    declared_phase_ids = {
        str(item.get("id") or "") for item in _as_list(plan.get("phase_index"))
        if isinstance(item, dict)
    }
    if declared_phase_ids != set(phase_data):
        raise SystemExit(
            "plan review static-admission-blocked: root phase_index does not match canonical phases"
        )
    task_paths: list[Path] = []
    task_index = rebuild_index(
        PLAN_CATALOG, "task", {"workspace_root": root}
    )
    task_rows: list[dict[str, Any]] = []
    for line in Path(str(task_index["path"])).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        if str(data.get("plan_id") or "") != plan_id:
            continue
        task_rows.append(data)
        path = canonical_artifact_path(
            family_policy(load_catalog(PLAN_CATALOG), "task"),
            {"workspace_root": root}, identity=str(data["id"]), state=state,
            bindings={"plan": plan_id, "phase": str(data["phase_id"])},
        )
        if not path.is_file():
            raise SystemExit(
                f"plan review static-admission-blocked: task is not in plan lifecycle state: {data['id']}"
            )
        task_paths.append(path)
    task_ids_by_phase = {
        phase_id: {
            str(row["id"]) for row in task_rows if str(row.get("phase_id") or "") == phase_id
        }
        for phase_id in phase_data
    }
    for phase_id, data in phase_data.items():
        declared = {
            str(item.get("id") or "") for item in _as_list(data.get("task_index"))
            if isinstance(item, dict)
        }
        if declared != task_ids_by_phase[phase_id]:
            raise SystemExit(
                f"plan review static-admission-blocked: {phase_id} task_index does not match canonical tasks"
            )
    all_task_ids = {str(row["id"]) for row in task_rows}
    validation_ids = {
        str(item.get("id") or "") for item in _as_list(plan.get("validation_strategy"))
        if isinstance(item, dict)
    }
    for coverage in _as_list(plan.get("source_coverage")):
        if not isinstance(coverage, dict):
            continue
        unknown_phases = set(map(str, _as_list(coverage.get("phase_ids")))) - set(phase_data)
        unknown_tasks = set(map(str, _as_list(coverage.get("task_ids")))) - all_task_ids
        unknown_validation = set(map(str, _as_list(coverage.get("validation_ids")))) - validation_ids
        if unknown_phases or unknown_tasks or unknown_validation:
            raise SystemExit(
                "plan review static-admission-blocked: source_coverage references unknown plan members or validation IDs"
            )
    phase_dependencies = {
        phase_id: [str(value) for value in _as_list(data.get("depends_on"))]
        for phase_id, data in phase_data.items()
    }
    for phase_id, required in phase_dependencies.items():
        invalid = [value for value in required if value == phase_id or value not in phase_data]
        if invalid:
            raise SystemExit(
                f"plan review static-admission-blocked: {phase_id} has impossible dependency {', '.join(invalid)}"
            )
    phase_visiting: set[str] = set()
    phase_visited: set[str] = set()

    def visit_phase(phase_id: str) -> None:
        if phase_id in phase_visiting:
            raise SystemExit(
                f"plan review static-admission-blocked: phase dependency cycle includes {phase_id}"
            )
        if phase_id in phase_visited:
            return
        phase_visiting.add(phase_id)
        for dependency in phase_dependencies[phase_id]:
            visit_phase(dependency)
        phase_visiting.remove(phase_id)
        phase_visited.add(phase_id)

    for phase_id in phase_dependencies:
        visit_phase(phase_id)
    compiled: list[dict[str, Any]] = []
    by_id: dict[str, Path] = {}
    for task_path in task_paths:
        try:
            brief = static_task_brief(root, task_path)
        except SystemExit as error:
            raise SystemExit(
                f"plan review static-admission-blocked: {task_path}: {error}"
            ) from error
        task_id = str(brief["task_id"])
        if task_id in by_id:
            raise SystemExit(
                f"plan review static-admission-blocked: duplicate task ID {task_id}: "
                f"{by_id[task_id]} and {task_path}"
            )
        by_id[task_id] = task_path
        compiled.append(brief)
    task_ids = set(by_id)
    dependencies = {
        str(brief["task_id"]): [str(value) for value in _as_list(brief.get("depends_on"))]
        for brief in compiled
    }
    for task_id, required in dependencies.items():
        invalid = [value for value in required if value == task_id or value not in task_ids]
        if invalid:
            raise SystemExit(
                f"plan review static-admission-blocked: {task_id} has impossible dependency "
                f"{', '.join(invalid)}"
            )
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise SystemExit(
                f"plan review static-admission-blocked: dependency cycle includes {task_id}"
            )
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in dependencies:
        visit(task_id)
    return compiled


def _compile_task_brief(
    args: argparse.Namespace,
    *,
    task_override: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    root, task_path, task, records, source_paths = _task_context(
        args, task_override=task_override
    )
    task_id = _artifact_id(task, "id", task_path)
    plan_id = _artifact_id(task, "plan_id", task_path)
    source_ids = [str(item) for item in _as_list(task.get("source_ids"))]
    if not source_ids:
        raise SystemExit(f"Task has no source_ids: {task_path}")
    for identifier in source_ids:
        _assert_not_excellence_proposal_id(identifier, "compiled briefs")
        if not SOURCE_ID_RE.fullmatch(identifier) or identifier not in records:
            sources = ", ".join(path.as_posix() for path in source_paths)
            raise SystemExit(f"Unresolved source ID {identifier}; searched: {sources}")

    files = task.get("files") if isinstance(task.get("files"), dict) else {}
    read_files = _task_scope_paths(
        _as_list(files.get("read")) or _as_list(task.get("source_files")), root, "read scope"
    )
    write_files = _task_scope_paths(
        _as_list(files.get("write")) or _as_list(task.get("target_files")), root, "write scope"
    )
    forbidden_files = _task_scope_paths(
        _as_list(files.get("forbidden")) or _as_list(task.get("forbidden_files")),
        root,
        "forbidden scope",
    )

    methodology = task.get("methodology") if isinstance(task.get("methodology"), dict) else {}
    allocated_skills = [item for item in _as_list(task.get("allocated_skills")) if isinstance(item, dict)]
    skill_names = (
        _as_list(methodology.get("skills"))
        or _as_list(methodology.get("required_skills"))
        or [item.get("name") for item in allocated_skills if item.get("name")]
    )
    rules = []
    for item in _as_list(task.get("allocated_rules")):
        if not isinstance(item, dict) or not item.get("id"):
            raise SystemExit(f"Invalid allocated_rules entry in {task_path}")
        requirement = item.get("requirement") or item.get("applies_when") or item.get("enforcement")
        rules.append({"id": item["id"], "requirement": requirement or "Apply this allocated rule."})

    interfaces = dict(task["interfaces"])

    validation_value = _compile_task_validation(task)
    executor_profile = _compile_executor_profile(task, task_path)
    evidence_applicability = task_evidence_applicability(task)

    resolved_goal = task.get("name") or task_id
    source_by_kind = {
        "requirements": [f"{sid}: {records[sid]}" for sid in source_ids if not sid.startswith(("CON-", "API-", "IFACE-", "TEST-"))],
        "constraints": [f"{sid}: {records[sid]}" for sid in source_ids if sid.startswith("CON-")],
    }
    truth_basis = _compile_truth_basis(task, records, source_paths)
    validation = [
        {
            key: (
                _compile_validation_references(value, records)
                if key == "proves"
                else value if key in {"id", "invariant_ids"}
                else _resolve_reference(value, records, source_paths)
            )
            for key, value in item.items()
        }
        for item in validation_value
    ]
    evidence_capability = _compile_evidence_capability(task, task_id, source_ids, validation)
    acceptance_review = task.get("acceptance_review")
    if acceptance_review in (None, {}):
        review_required = False
    elif not isinstance(acceptance_review, dict):
        raise SystemExit(f"Task acceptance_review must be a mapping: {task_path}")
    else:
        review_required = acceptance_review.get("required", False)
        if not isinstance(review_required, bool):
            raise SystemExit(f"Task acceptance_review.required must be boolean: {task_path}")
    semantic_authority = _compile_semantic_authority(source_ids, records, truth_basis)
    capability_projection = _compile_capability_projection(executor_profile, rules, skill_names)
    task_brief = {
            "task_id": task_id,
            "plan_id": plan_id,
            "depends_on": [str(value) for value in _as_list(task.get("depends_on"))],
            "source_ids": source_ids,
            "goal": resolved_goal,
            "truth_basis": truth_basis,
            "semantic_authority": semantic_authority,
            "requirements": source_by_kind["requirements"],
            "constraints": source_by_kind["constraints"],
            "interfaces": {
                "consumes": _retain_source_references(_as_list(interfaces.get("consumes")), records),
                "produces": _retain_source_references(_as_list(interfaces.get("produces")), records),
            },
            "files": {"read": read_files, "write": write_files, "forbidden": forbidden_files},
            "methodology": {"primary": methodology.get("primary", "direct"), "skills": skill_names},
            "allocated_rules": rules,
            "capability_projection": capability_projection,
            "executor_profile": executor_profile,
            "evidence_applicability": evidence_applicability,
            "workspace": {"root": str(root)},
            "runtime_context": {
                "authority": "compiled",
                "histories": "runtime_lazy",
                "executor_retrieval": "forbidden",
            },
            "validation": validation,
            "evidence_capability": evidence_capability,
            "handoff_contract": "executor-result-v1",
            "review_required": review_required,
    }
    omitted = 0
    serialized_task = json.dumps(task, sort_keys=True, ensure_ascii=False)
    for identifier in source_ids:
        duplicate_references = max(0, serialized_task.count(identifier) - 1)
        omitted += duplicate_references * max(0, len(records[identifier].encode("utf-8")) - len(identifier.encode("utf-8")))
    brief = {
        "task_brief": task_brief,
        "compiled_context_metrics": compiled_context_metrics(
            task_brief, omitted_by_reference_bytes=omitted
        ),
    }
    for identifier in source_ids:
        if not _contains_resolved_source_record(brief, records[identifier]):
            raise SystemExit(
                f"Source ID {identifier} from {', '.join(path.as_posix() for path in source_paths)} "
                "is not allocated to a resolved task-brief field"
            )
    _assert_no_credential_values(brief, "task brief")
    target = root / ".work-bundle/runtime/execution" / plan_id / task_id / "task-brief.yaml"
    return target, brief


def build_task_brief(args: argparse.Namespace) -> Path:
    target, brief = _compile_task_brief(args)
    _maybe_bind_execution_from_args(args, brief["task_brief"])
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(target, ("\n".join(_dump_yaml(brief)) + "\n").encode("utf-8"))
    return target


def compile_task_candidate(
    root: Path, task_path: Path, candidate: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    """Compile a task amendment without mutating canonical or runtime state."""

    args = argparse.Namespace(
        workspace_root=str(root), task=str(task_path),
        handoff=None, base=None, head=None, _resolved_root=str(root),
    )
    return _compile_task_brief(args, task_override=candidate)




































def cmd_build_task_brief(args: argparse.Namespace) -> None:
    target = build_task_brief(args)
    print(target.relative_to(resolve_workspace_root(args)).as_posix())












def _observation_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "workspace_id": getattr(args, "workspace_id", None) or None,
        "execution_id": getattr(args, "execution_id", None) or None,
        "repository_id": getattr(args, "repository_id", None) or None,
        "execution_runtime_root": getattr(args, "execution_runtime_root", None) or None,
        "accepted_dependency_deltas": (
            getattr(args, "accepted_dependency_deltas", None) or None
        ),
        "mutation_events": getattr(args, "mutation_events", None),
        "prior_ownership": getattr(args, "prior_ownership", None) or None,
        "repair_continuity": getattr(args, "repair_continuity", None) or None,
        "authorized_replacements": getattr(args, "authorized_replacements", None) or None,
    }


def _maybe_bind_execution_from_args(args: argparse.Namespace, brief: dict[str, Any]) -> None:
    kwargs = _observation_kwargs(args)
    if not (kwargs["workspace_id"] and kwargs["execution_id"] and kwargs["repository_id"]):
        return
    runtime = Path(
        kwargs["execution_runtime_root"] or str(_execution_workspace_module().default_runtime_root())
    )
    control_root = Path(str((brief.get("workspace") or {}).get("root") or resolve_workspace_root(args)))
    binding = create_or_load_task_execution_binding(
        control_root=control_root,
        plan_id=str(brief["plan_id"]),
        task_id=str(brief["task_id"]),
        workspace_id=str(kwargs["workspace_id"]),
        execution_id=str(kwargs["execution_id"]),
        repository_id=str(kwargs["repository_id"]),
        runtime_root=runtime,
        write_scope=[str(path) for path in _as_list((brief.get("files") or {}).get("write"))],
        forbidden_scope=[str(path) for path in _as_list((brief.get("files") or {}).get("forbidden"))],
    )
    capture_task_baseline_once(binding, control_root)


def build_implementation_review_candidate(
    *,
    source_root: Path,
    kind: str,
    base_commit: str,
    changed_paths: Iterable[str],
) -> dict[str, Any]:
    """Freeze an exact commit or worktree manifest without requiring clean HEAD.

    This function validates identity and scope facts only. It does not judge the
    implementation, its tests, or its acceptability.
    """

    root = source_root.expanduser().resolve()
    if kind not in {"commit", "worktree"}:
        raise SystemExit(f"Unsupported implementation candidate kind: {kind}")
    if re.fullmatch(r"[0-9a-f]{40}", base_commit) is None:
        raise SystemExit("Implementation candidate requires a 40-character base commit")
    resolved = subprocess.run(
        ["git", "-C", str(root), "rev-parse", f"{base_commit}^{{commit}}"],
        capture_output=True, text=True, check=False,
    )
    if resolved.returncode or resolved.stdout.strip() != base_commit:
        raise SystemExit("Implementation candidate base commit is not a canonical Git commit")
    normalized: list[str] = []
    for raw in changed_paths:
        path = Path(str(raw))
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise SystemExit(f"Implementation candidate path is not canonical: {raw}")
        value = path.as_posix()
        if value in normalized:
            raise SystemExit(f"Implementation candidate path is duplicated: {value}")
        normalized.append(value)
    manifest: list[dict[str, str]] = []
    for relative in sorted(normalized):
        if kind == "commit":
            observed = subprocess.run(
                ["git", "-C", str(root), "show", f"{base_commit}:{relative}"],
                capture_output=True, check=False,
            )
            if observed.returncode:
                raise SystemExit(f"Implementation candidate commit path is unavailable: {relative}")
            content = observed.stdout
            entry = {
                "path": relative,
                "state": "present",
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        else:
            worktree_path = root / relative
            path = worktree_path.resolve(strict=False)
            if root not in path.parents or worktree_path.is_symlink():
                raise SystemExit(f"Implementation candidate path is unavailable: {relative}")
            if worktree_path.is_file():
                content = worktree_path.read_bytes()
                entry = {
                    "path": relative,
                    "state": "present",
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            elif worktree_path.exists():
                raise SystemExit(f"Implementation candidate path is unavailable: {relative}")
            else:
                base_type = subprocess.run(
                    ["git", "-C", str(root), "cat-file", "-t", f"{base_commit}:{relative}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if base_type.returncode or base_type.stdout.strip() != "blob":
                    raise SystemExit(f"Implementation candidate path is unavailable: {relative}")
                entry = {"path": relative, "state": "deleted"}
        manifest.append(entry)
    manifest_bytes = "".join(
        (
            f"present {item['sha256']}  {item['path']}\n"
            if item["state"] == "present"
            else f"deleted -  {item['path']}\n"
        )
        for item in manifest
    ).encode("utf-8")
    return {
        "kind": kind,
        "base_commit": base_commit,
        "manifest": manifest,
        "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }


def cmd_build_implementation_review_candidate(args: argparse.Namespace) -> None:
    source_root = Path(str(args.source_root)).expanduser().resolve()
    candidate = build_implementation_review_candidate(
        source_root=source_root,
        kind=str(args.kind),
        base_commit=str(args.base_commit),
        changed_paths=getattr(args, "changed_path", []),
    )
    print(json.dumps(candidate, ensure_ascii=False, sort_keys=True))
