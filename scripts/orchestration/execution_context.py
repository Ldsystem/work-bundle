#!/usr/bin/env python3
"""Compile disposable, task-bounded executor and reviewer context packets."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping
from datetime import datetime, timezone


from core import is_relative_to, read_front_matter, resolve_workspace_root
from artifact_inputs import (_split_top_level, _split_key_value, _parse_scalar, parse_yaml_subset,
                             _read_structured, _as_list, _input_path, _resolve_spec_paths)
from repository_preflight import capture_repository_evidence, task_caused_paths
from task_ownership import (
    OwnershipBlocker,
    RepairContinuity,
    normalize_subagent_provenance,
    validate_task_acceptance_ownership,
)


SOURCE_ID_TOKEN = r"[A-Z][A-Z0-9_-]*-\d+[A-Z]?"
SOURCE_ID_RE = re.compile(rf"^{SOURCE_ID_TOKEN}$")
AUTH_ALIAS_RE = re.compile(r"^AUTH-\d{3}$")
EXCELLENCE_PROPOSAL_RE = re.compile(r"^EXC-\d+$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
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
        if not text:
            raise SystemExit(f"Task {label} contains an empty path")
        if _protected_project_path(text, root):
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
    for status in ("active", "archived"):
        for candidate in sorted((plan_root / status).glob("*.md")):
            data, _ = _read_structured(candidate)
            if str(data.get("id", "")) == plan_id:
                matches.append((candidate, data))
    if len(matches) != 1:
        raise SystemExit(f"Expected one root plan for {plan_id}; found {len(matches)} under {plan_root}")
    return matches[0]




def _strip_markup(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).strip()


def _source_records(path: Path, body: str) -> dict[str, str]:
    records: dict[str, str] = {}

    def add(identifier: str, value: str) -> None:
        if AUTH_ALIAS_RE.fullmatch(identifier) or EXCELLENCE_PROPOSAL_RE.fullmatch(identifier):
            return
        value = _strip_markup(value)
        if not value:
            return
        previous = records.get(identifier)
        if previous is not None and previous != value:
            raise SystemExit(f"Ambiguous source ID {identifier} in {path}")
        records[identifier] = value

    lines = body.splitlines()
    for index, line in enumerate(lines):
        block = re.match(rf"^(\s+)({SOURCE_ID_TOKEN})\s*:\s*$", line)
        if not block:
            continue
        base_indent = len(block.group(1))
        detail: list[str] = []
        for child in lines[index + 1 :]:
            if not child.strip():
                continue
            child_indent = len(child) - len(child.lstrip())
            if child_indent <= base_indent:
                break
            detail.append(child.strip())
        if detail:
            add(block.group(2), " ".join(detail))

    for line in lines:
        bullet = re.match(
            rf"^\s*[-*]\s+\*\*({SOURCE_ID_TOKEN})(?::\*\*\s*|\*\*\s*:\s*)(.+)$",
            line,
        )
        if bullet:
            add(bullet.group(1), bullet.group(2))
            continue
        titled_bullet = re.match(
            rf"^\s*[-*]\s+\*\*({SOURCE_ID_TOKEN})\s+[—-]\s+(.+?)(?::\*\*\s*|\*\*\s*:\s*)(.+)$",
            line,
        )
        if titled_bullet:
            title = titled_bullet.group(2).strip()
            detail = titled_bullet.group(3).strip()
            add(titled_bullet.group(1), f"{title}: {detail}")
            continue
        bold_plain = re.match(
            rf"^\s*\*\*({SOURCE_ID_TOKEN})(?::\*\*\s*|\*\*\s*:\s*)(.+)$",
            line,
        )
        if bold_plain:
            add(bold_plain.group(1), bold_plain.group(2))
            continue
        titled_plain = re.match(
            rf"^\s*\*\*({SOURCE_ID_TOKEN})\s+[—-]\s+(.+?)(?::\*\*\s*|\*\*\s*:\s*)(.+)$",
            line,
        )
        if titled_plain:
            title = titled_plain.group(2).strip()
            detail = titled_plain.group(3).strip()
            add(titled_plain.group(1), f"{title}: {detail}")
            continue
        heading = re.match(
            rf"^#{{2,6}}\s+({SOURCE_ID_TOKEN})(?:(?:\s+[:—-]?\s*)|(?:[:—-]\s*))(.*)$",
            line,
        )
        if heading and heading.group(2).strip():
            add(heading.group(1), heading.group(2))
            continue
        plain = re.match(rf"^\s*({SOURCE_ID_TOKEN})\s*:\s*(.+)$", line)
        if plain:
            add(plain.group(1), plain.group(2))
            continue
        if line.strip().startswith("|"):
            cells = [cell.strip().strip("*") for cell in line.strip().strip("|").split("|")]
            if cells and SOURCE_ID_RE.fullmatch(cells[0]):
                add(cells[0], " | ".join(cell for cell in cells[1:] if cell))
    return records


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


def _handoff_identity_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "~"}:
        return None
    return text


def explicit_handoff_plan_identities(handoff: dict[str, Any]) -> list[str]:
    related = handoff.get("related") if isinstance(handoff.get("related"), dict) else {}
    identities: list[str] = []
    for raw in (related.get("plan"), handoff.get("related_plan")):
        text = _handoff_identity_text(raw)
        if text and text not in identities:
            identities.append(text)
    return identities


def unique_explicit_handoff_plan_id(handoff: dict[str, Any]) -> str | None:
    identities = explicit_handoff_plan_identities(handoff)
    if len(identities) != 1:
        return None
    return identities[0]


def _assert_task_handoff_identity(handoff: dict[str, Any], task_id: str, plan_id: str) -> None:
    related = handoff.get("related") if isinstance(handoff.get("related"), dict) else {}
    related_task = related.get("task") or handoff.get("related_task")
    if related_task != task_id:
        raise SystemExit(f"Handoff task mismatch: expected {task_id}, got {related_task or 'missing'}")
    identities = explicit_handoff_plan_identities(handoff)
    if not identities:
        raise SystemExit(f"Handoff plan identity missing: expected {plan_id}")
    if len(identities) > 1:
        raise SystemExit(f"Handoff plan identity conflict: {' vs '.join(identities)}")
    if identities[0] != plan_id:
        raise SystemExit(f"Handoff plan mismatch: expected {plan_id}, got {identities[0]}")


def _handoff_review_required(handoff: dict[str, Any]) -> bool:
    review = handoff.get("acceptance_review")
    if not isinstance(review, dict) or not review:
        return False
    return review.get("required", False) is True


def _handoff_ineligible_for_closure(handoff: dict[str, Any]) -> bool:
    result = handoff.get("result") if isinstance(handoff.get("result"), dict) else {}
    state = result.get("state")
    review = handoff.get("acceptance_review") if isinstance(handoff.get("acceptance_review"), dict) else {}
    verdict = review.get("verdict")
    unresolved = _as_list(handoff.get("unresolved"))
    if state in {"blocked", "failed", "partial"}:
        return True
    if verdict in {"repair", "blocked"}:
        return True
    if unresolved:
        return True
    return False


def _handoff_eligible_for_closure(handoff: dict[str, Any], *, review_required: bool | None = None) -> bool:
    if _handoff_ineligible_for_closure(handoff):
        return False
    required = _handoff_review_required(handoff) if review_required is None else review_required
    if required:
        review = handoff.get("acceptance_review")
        return isinstance(review, dict) and review.get("verdict") == "accept"
    result = handoff.get("result") if isinstance(handoff.get("result"), dict) else {}
    return result.get("state") == "completed"


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


def _allocated_decision_aliases(truth_basis: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for value in _as_list(truth_basis.get("decision_authority")):
        alias = str(value).split(":", 1)[0].strip()
        if AUTH_ALIAS_RE.fullmatch(alias):
            aliases.add(alias)
    return aliases


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
    review_package: str | None = None,
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
        "review_package_bytes": len(review_package.encode("utf-8")) if review_package is not None else 0,
        "omitted_by_reference_bytes": max(0, int(omitted_by_reference_bytes)),
        "expansion_reason": expansion_reason,
    }


def project_validation_evidence(
    items: list[dict[str, Any]],
    *,
    evidence_capability: dict[str, Any],
    observed: list[dict[str, Any]] | None = None,
    expansion_reason: str | None = None,
) -> list[dict[str, Any]]:
    """Project successes as compact receipts and expand only explicit failures."""

    if expansion_reason not in CONTEXT_EXPANSION_REASONS:
        raise SystemExit("evidence projection expansion_reason is invalid")
    observed_by_id = {
        str(item.get("id")): item for item in (observed or []) if isinstance(item, dict) and item.get("id")
    }
    invariant_by_evidence: dict[str, dict[str, Any]] = {}
    for invariant in _as_list(evidence_capability.get("invariants")):
        if not isinstance(invariant, dict):
            continue
        for evidence_id in _as_list(invariant.get("evidence_ids")):
            invariant_by_evidence.setdefault(str(evidence_id), invariant)
    projected: list[dict[str, Any]] = []
    for position, item in enumerate(items, start=1):
        evidence_id = str(item.get("id") or f"validation-{position:03d}")
        result = str(item.get("result") or "ambiguous")
        if result not in {"passed", "skipped"}:
            reason = expansion_reason or ("failed_validation" if result == "failed" else "ambiguity")
            if reason not in CONTEXT_EXPANSION_REASONS - {None}:
                raise SystemExit("evidence projection expansion_reason is invalid")
            projected.append({
                "id": evidence_id,
                "digest": semantic_digest({"command": item.get("command"), "result": result}),
                "result": result,
                "expansion_reason": reason,
                "details": dict(item),
            })
            continue
        invariant = invariant_by_evidence.get(evidence_id, {})
        observation = observed_by_id.get(evidence_id, {})
        projected.append({
            "id": evidence_id,
            "digest": semantic_digest({"command": item.get("command"), "result": result}),
            "result": result,
            "boundary": invariant.get("boundary", "component"),
            "freshness": invariant.get("freshness", "current_task_batch"),
            "invalidation_receipt": observation.get("observation_id") or semantic_digest(
                {"evidence_id": evidence_id, "result": result}
            ),
            "expansion_reason": None,
        })
    return projected


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


def _validate_evidence_closure(
    handoff: dict[str, Any],
    task: dict[str, Any],
    state: str,
    reported_commands: dict[str, dict[str, Any]],
    observed_validation: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    capability = task.get("evidence_capability")
    if not isinstance(capability, dict):
        raise SystemExit("Compiled task is missing evidence_capability authority")
    if capability.get("result") == "no_validation_bearing_obligation":
        return {"result": "no_validation_bearing_obligation", "invariants": []}
    if capability.get("result") != "mapped" or state != "completed":
        return {"result": "not-terminal", "invariants": []}
    if observed_validation is None:
        raise SystemExit("evidence-closure-blocked: completed mapped invariants require independent harness observation")
    closure = handoff.get("evidence_closure")
    if not isinstance(closure, dict):
        raise SystemExit("Executor result is missing evidence_closure for mapped invariants")
    allocated = {
        str(item.get("id")): item
        for item in _as_list(capability.get("invariants"))
        if isinstance(item, dict) and _nonempty_text(item.get("id"))
    }
    entries = [item for item in _as_list(closure.get("invariants")) if isinstance(item, dict)]
    by_id = {str(item.get("id")): item for item in entries if _nonempty_text(item.get("id"))}
    if len(by_id) != len(entries) or set(by_id) != set(allocated):
        raise SystemExit("evidence-closure-blocked: mapped invariant closure IDs are missing or unexpected; route plan")
    validation_by_id = {
        str(item.get("id")): item
        for item in _as_list(task.get("validation"))
        if isinstance(item, dict) and _nonempty_text(item.get("id"))
    }
    observed_by_id = {
        str(item.get("id")): item
        for item in (observed_validation or [])
        if isinstance(item, dict) and _nonempty_text(item.get("id"))
    }
    for invariant_id, expected in allocated.items():
        actual = by_id[invariant_id]
        if actual.get("boundary") != expected.get("boundary"):
            raise SystemExit(f"evidence-closure-blocked: {invariant_id} is wrong-boundary; route plan")
        if actual.get("freshness") != expected.get("freshness"):
            raise SystemExit(f"evidence-closure-blocked: {invariant_id} is stale; route task")
        evidence_ids = [str(value) for value in _as_list(actual.get("evidence_ids"))]
        if evidence_ids != [str(value) for value in _as_list(expected.get("evidence_ids"))]:
            raise SystemExit(f"evidence-closure-blocked: {invariant_id} evidence mapping is missing; route plan")
        closure_result = str(actual.get("closure_result") or "missing")
        if closure_result not in EVIDENCE_CLOSURE_RESULTS:
            raise SystemExit(f"evidence-closure-blocked: {invariant_id} has invalid closure_result")
        if closure_result != "passed":
            repair_owner = str(actual.get("repair_owner") or "task")
            expected_owner = EVIDENCE_REPAIR_OWNERS[closure_result]
            if repair_owner != expected_owner:
                raise SystemExit(
                    f"evidence-closure-blocked: {invariant_id} {closure_result} must route {expected_owner}"
                )
            raise SystemExit(
                f"evidence-closure-blocked: {invariant_id} is {closure_result}; route {repair_owner}"
            )
        for evidence_id in evidence_ids:
            validation = validation_by_id.get(evidence_id)
            if validation is None:
                raise SystemExit(f"evidence-closure-blocked: {invariant_id} evidence {evidence_id} is missing; route plan")
            command = str(validation.get("command") or "").strip()
            reported = reported_commands.get(command)
            if not isinstance(reported, dict):
                raise SystemExit(f"evidence-closure-blocked: {invariant_id} evidence {evidence_id} is unexecuted; route task")
            if str(reported.get("id") or "") != evidence_id or invariant_id not in _as_list(reported.get("invariant_ids")):
                raise SystemExit(f"evidence-closure-blocked: reported evidence identity for {invariant_id} is missing; route task")
            if reported.get("result") != "passed":
                raise SystemExit(f"evidence-closure-blocked: {invariant_id} evidence {evidence_id} failed; route task")
            if observed_validation is not None:
                observed = observed_by_id.get(evidence_id)
                if not isinstance(observed, dict) or invariant_id not in _as_list(observed.get("invariant_ids")):
                    raise SystemExit(f"evidence-closure-blocked: harness evidence for {invariant_id} is missing; route task")
                if observed.get("result") != "passed":
                    raise SystemExit(f"evidence-closure-blocked: harness evidence {evidence_id} failed; route task")
    if closure.get("result") != "passed":
        raise SystemExit("evidence-closure-blocked: aggregate closure result is not passed")
    return {"result": "passed", "invariants": entries}


def evaluate_knowledge_closure_state(
    *,
    upstream_disposition: str,
    accepted_task_handoffs: list[dict[str, Any]],
    closure_return: str = "missing",
    review_required_by_task: dict[str, bool] | None = None,
) -> dict[str, Any]:
    if upstream_disposition not in {"required", "not-needed", "completed", "blocked"}:
        raise SystemExit("Invalid upstream Knowledge Base Update disposition")
    if closure_return not in {"missing", "completed", "not-needed", "blocked"}:
        raise SystemExit("Invalid knowledge closure return state")

    triggers: list[dict[str, str]] = []
    for handoff in accepted_task_handoffs:
        related = handoff.get("related") if isinstance(handoff.get("related"), dict) else {}
        task_id = str(related.get("task") or "")
        compiled_required = None
        if review_required_by_task is not None and task_id in review_required_by_task:
            compiled_required = review_required_by_task[task_id]
        if not _handoff_eligible_for_closure(handoff, review_required=compiled_required):
            continue
        disposition = handoff.get("knowledge_disposition")
        if not isinstance(disposition, dict):
            raise SystemExit("Accepted task handoff knowledge disposition is required")
        action = disposition.get("action")
        if action is None and "action" in disposition:
            action = "none"
        if action not in KNOWLEDGE_DISPOSITION_ACTIONS:
            raise SystemExit("Accepted task handoff knowledge disposition action is invalid")
        if action != "none":
            triggers.append({"task": task_id or "unknown", "action": str(action)})

    closure_required = upstream_disposition in {"required", "blocked"} or bool(triggers)
    if not closure_required:
        disposition = upstream_disposition
        if disposition == "completed":
            return {"disposition": "completed", "archive_blocked": False, "triggers": triggers}
        return {"disposition": "not-needed", "archive_blocked": False, "triggers": triggers}
    if closure_return in {"completed", "not-needed"}:
        return {"disposition": closure_return, "archive_blocked": False, "triggers": triggers}
    if closure_return == "blocked":
        return {"disposition": "blocked", "archive_blocked": True, "triggers": triggers}
    return {"disposition": "required", "archive_blocked": True, "triggers": triggers}


def _validated_knowledge_disposition(
    handoff: dict[str, Any],
    accepted_source_ids: list[str],
    accepted_authority_paths: list[str],
    allocated_decision_aliases: set[str],
) -> dict[str, Any]:
    raw = handoff.get("knowledge_disposition")
    if not isinstance(raw, dict):
        raise SystemExit("Executor result knowledge disposition is required")
    action = raw.get("action")
    if action is None and "action" in raw:
        action = "none"
    if action not in KNOWLEDGE_DISPOSITION_ACTIONS:
        raise SystemExit(
            "Executor result knowledge disposition action must be none, update, supersede, or reclassify"
        )
    reason = raw.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise SystemExit("Executor result knowledge disposition reason must be non-empty")
    affected = _as_list(raw.get("affected_authority"))
    if any(not isinstance(value, str) or not value.strip() for value in affected):
        raise SystemExit("Executor result affected_authority must contain only non-empty strings")
    if action == "none" and affected:
        raise SystemExit("Executor result knowledge disposition none must not name affected authority")
    if action != "none" and not affected:
        raise SystemExit("Executor result knowledge disposition change must name affected authority")
    disposition_text = "\n".join([reason, *affected])
    if KNOWLEDGE_PERSISTENCE_INSTRUCTION_RE.search(disposition_text):
        raise SystemExit("Executor result knowledge disposition must not instruct knowledge access or writes")
    for authority in affected:
        if AUTH_ALIAS_RE.fullmatch(authority):
            if authority not in allocated_decision_aliases:
                raise SystemExit("Executor result knowledge disposition cites unallocated decision authority")
            continue
        if SOURCE_ID_RE.fullmatch(authority):
            if authority not in accepted_source_ids:
                raise SystemExit("Executor result knowledge disposition cites unallocated source authority")
            continue
        if authority not in accepted_authority_paths:
            raise SystemExit("Executor result knowledge disposition path must be in compiled task scope")
    return {"action": action, "reason": reason.strip(), "affected_authority": affected}


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


def _scopes_overlap(left: list[str], right: list[str]) -> bool:
    first = {str(path).removeprefix("./") for path in left}
    second = {str(path).removeprefix("./") for path in right}
    if first & second:
        return True
    for item in first:
        for other in second:
            if _write_scope_match(item, [other]) or _write_scope_match(other, [item]):
                return True
    return False


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
    from review_runtime import require_plan_reviews
    require_plan_reviews(control_root, _find_plan(control_root, plan_id)[0])
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
        "write_scope": list(write_scope or []),
        "forbidden_scope": list(forbidden_scope or []),
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


FILE_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _write_scope_file_digest(execution_root: Path, task: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    files = task.get("files") if isinstance(task.get("files"), dict) else {}
    for relative in _as_list(files.get("write")):
        digest.update(str(relative).encode("utf-8"))
        digest.update(b"\0")
        path = execution_root / str(relative)
        if path.is_file() and not path.is_symlink():
            digest.update(path.read_bytes())
        else:
            digest.update(b"MISSING")
        digest.update(b"\n")
    return digest.hexdigest()


def _run_named_inspection(mechanism: str, execution_root: Path, task: dict[str, Any], item: dict[str, Any]) -> str:
    if mechanism != "named-harness-file-digest":
        raise SystemExit(f"Unknown inspection mechanism: {mechanism}")
    expected = str(item.get("digest") or "").strip().lower()
    if not FILE_DIGEST_RE.fullmatch(expected):
        raise SystemExit("named-harness-file-digest requires a 64-character hex digest")
    actual = _write_scope_file_digest(execution_root, task)
    return "passed" if actual == expected else "failed"


def _observe_validation_item(item: dict[str, Any], execution_root: Path, task: dict[str, Any], receipt: dict | None = None) -> dict[str, Any]:
    command = str(item.get("command") or "").strip()
    kind = str(item.get("kind") or "").strip().lower()
    if kind not in VALIDATION_KINDS:
        raise SystemExit(
            "Task validation kind must be process or inspection; untyped structured validation is legacy-untyped"
        )
    allowed = _acceptable_validation_results(item)
    expected = str(item.get("expected") or "").strip().lower()
    if expected in {"skip", "skipped"} and "skipped" in allowed:
        observed = {"command": command, "result": "skipped", "kind": kind}
        if kind == "inspection":
            observed["mechanism"] = str(item.get("mechanism") or "").strip()
        observed.update({"id": item.get("id"), "invariant_ids": list(_as_list(item.get("invariant_ids")))})
        return observed
    if kind == "inspection":
        mechanism = str(item.get("mechanism") or "").strip()
        if not mechanism:
            raise SystemExit("Inspection validation requires a named harness-owned mechanism")
        result_value = _run_named_inspection(mechanism, execution_root, task, item)
        return {"command": command, "result": result_value, "kind": "inspection", "mechanism": mechanism, "id": item.get("id"), "invariant_ids": list(_as_list(item.get("invariant_ids")))}
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    completed = subprocess.run(
        command,
        shell=True,
        cwd=str(execution_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if receipt is not None:
        receipt.update(exit_code=completed.returncode,
                       stdout_digest=hashlib.sha256(completed.stdout.encode()).hexdigest(),
                       stderr_digest=hashlib.sha256(completed.stderr.encode()).hexdigest(),
                       started_at=started_at, completed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    return {
        "command": command,
        "result": "passed" if completed.returncode == 0 else "failed",
        "kind": "process",
        "id": item.get("id"),
        "invariant_ids": list(_as_list(item.get("invariant_ids"))),
    }


def _path_is_forbidden(relative: str, forbidden: list[str]) -> bool:
    normalized = relative.removeprefix("./")
    for pattern in forbidden:
        pat = str(pattern).removeprefix("./")
        if pat.endswith("/**"):
            prefix = pat[:-3]
            if normalized == prefix or normalized.startswith(f"{prefix}/"):
                return True
        elif normalized == pat:
            return True
    return False


def _assert_task_caused_delta_in_write_scope(
    caused: list[str],
    task_files: dict[str, Any],
    *,
    accepted_dependency_paths: set[str] | None = None,
) -> None:
    write_paths = [str(path) for path in _as_list(task_files.get("write"))]
    forbidden = [str(path) for path in _as_list(task_files.get("forbidden"))]
    for relative in caused:
        if relative in (accepted_dependency_paths or set()):
            continue
        if _path_is_forbidden(relative, forbidden) or not _write_scope_match(relative, write_paths):
            raise SystemExit(f"Unauthorized task-caused delta outside write scope: {relative}")


def _exact_handoff_reference(
    handoff_root: Path,
    reference: object,
) -> tuple[Path, dict[str, Any]]:
    if not isinstance(reference, Mapping) or set(reference) != {"handoff_id", "handoff_sha256"}:
        raise SystemExit("accepted dependency handoff reference must use the closed identity shape")
    handoff_id = str(reference["handoff_id"])
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(handoff_root.glob("executor/*/*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            document, _ = _read_structured(path)
        except (OSError, SystemExit, ValueError):
            continue
        if document.get("id") == handoff_id:
            matches.append((path, document))
    if len(matches) != 1:
        raise SystemExit(f"accepted dependency handoff identity is missing or ambiguous: {handoff_id}")
    path, handoff = matches[0]
    if hashlib.sha256(path.read_bytes()).hexdigest() != str(reference["handoff_sha256"]):
        raise SystemExit(f"accepted dependency handoff identity is stale: {handoff_id}")
    return path, handoff


def _review_without_history(review: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in review.items() if key != "previous_review"}


RECOVERY_RECEIPT_SCHEMA = "accepted-result-recovery-receipt-v1"
RECOVERY_RECEIPT_KEYS = {
    "receipt_id",
    "schema",
    "plan_id",
    "task_id",
    "binding_id",
    "binding_sha256",
    "baseline_head",
    "baseline_tree",
    "expected_base_head",
    "expected_base_tree",
    "expected_base_query",
    "proposed_recovered_result",
    "observed_at",
    "freshness",
}
LEGACY_RECOVERY_RECEIPT_KEYS = {
    "receipt_id",
    "schema",
    "plan_id",
    "task_id",
    "binding_id",
    "binding_sha256",
    "baseline_head",
    "baseline_tree",
    "expected_base_head",
    "expected_base_tree",
    "queried_historical_revision",
    "handoff_stores",
    "handoff_index",
    "absence_result",
    "observed_at",
    "freshness",
}


def _recovery_receipt_path(
    control_root: Path, plan_id: str, task_id: str, receipt_id: str
) -> Path:
    if not all(SAFE_ID_RE.fullmatch(value) for value in (plan_id, task_id, receipt_id)):
        raise SystemExit("accepted-result recovery receipt identity is unsafe")
    return (
        control_root.expanduser().resolve()
        / ".work-bundle/runtime/execution"
        / plan_id
        / task_id
        / "accepted-result-recovery"
        / f"{receipt_id}.json"
    )


def _is_recoverable_accepted_base(
    handoff: Mapping[str, Any],
    plan_id: str,
    task_id: str,
    expected_base_head: str,
    expected_base_tree: str,
) -> bool:
    related = handoff.get("related") if isinstance(handoff.get("related"), Mapping) else {}
    result = handoff.get("result") if isinstance(handoff.get("result"), Mapping) else {}
    review = (
        handoff.get("acceptance_review")
        if isinstance(handoff.get("acceptance_review"), Mapping)
        else {}
    )
    reset = review.get("review_reset") if isinstance(review.get("review_reset"), Mapping) else {}
    if reset.get("reason_class") == "authority":
        # This is the newly reconstructed whole-task result, never the missing
        # historical accepted base whose absence authorizes reconstruction.
        return False
    if (
        handoff.get("type") != "executor-result"
        or related.get("plan") != plan_id
        or related.get("task") != task_id
        or result.get("state") != "completed"
        or review.get("verdict") != "accept"
    ):
        return False
    identity = review.get("target_identity") if isinstance(review.get("target_identity"), Mapping) else {}
    if (
        identity.get("artifact_id") != task_id
        or identity.get("revision") != expected_base_head
        or identity.get("source_tree") != expected_base_tree
        or review.get("reviewed_head") != expected_base_head
    ):
        return False
    try:
        from review_runtime import ReviewContractError, validate_task_acceptance_review

        validate_task_acceptance_review(review)
    except (ReviewContractError, KeyError, TypeError, ValueError):
        return False
    return True


def _accepted_base_query_snapshot(
    control_root: Path,
    plan_id: str,
    task_id: str,
    expected_base_head: str,
    expected_base_tree: str,
    proposed_handoff_id: str,
    proposed_review_id: str,
    final_head: str,
    final_tree: str,
) -> dict[str, Any]:
    handoff_root = control_root / ".work-bundle/orchestration/handoff"
    recoverable_ids: list[str] = []
    proposal_records: list[dict[str, Any]] = []
    for status in ("active", "archived"):
        for path in sorted((handoff_root / "executor" / status).glob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                handoff, _ = _read_structured(path)
            except (OSError, SystemExit, ValueError):
                continue
            handoff_id = str(handoff.get("id") or "")
            if _is_recoverable_accepted_base(
                handoff,
                plan_id,
                task_id,
                expected_base_head,
                expected_base_tree,
            ):
                recoverable_ids.append(handoff_id)
            related = handoff.get("related") if isinstance(handoff.get("related"), Mapping) else {}
            review = (
                handoff.get("acceptance_review")
                if isinstance(handoff.get("acceptance_review"), Mapping)
                else {}
            )
            identity = (
                review.get("target_identity")
                if isinstance(review.get("target_identity"), Mapping)
                else {}
            )
            if handoff_id != proposed_handoff_id and review.get("review_id") != proposed_review_id:
                continue
            result = handoff.get("result") if isinstance(handoff.get("result"), Mapping) else {}
            proposal_records.append(
                {
                    "handoff_id": handoff_id,
                    "review_id": str(review.get("review_id") or ""),
                    "path": path.relative_to(control_root).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "exact": (
                        handoff_id == proposed_handoff_id
                        and handoff.get("type") == "executor-result"
                        and related.get("plan") == plan_id
                        and related.get("task") == task_id
                        and result.get("state") == "completed"
                        and review.get("review_id") == proposed_review_id
                        and review.get("reviewed_head") == final_head
                        and identity.get("artifact_id") == task_id
                        and identity.get("revision") == final_head
                        and identity.get("source_tree") == final_tree
                    ),
                }
            )

    index_path = handoff_root / "index.jsonl"
    if not index_path.is_file() or index_path.is_symlink():
        raise SystemExit("accepted-result recovery requires the native handoff index")
    proposal_index_entries: list[dict[str, Any]] = []
    for number, line in enumerate(index_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise SystemExit(f"accepted-result recovery handoff index is invalid at line {number}") from error
        if not isinstance(entry, dict):
            raise SystemExit(f"accepted-result recovery handoff index is invalid at line {number}")
        if entry.get("id") == proposed_handoff_id:
            proposal_index_entries.append(entry)

    exact_records = [record for record in proposal_records if record["exact"]]
    proposal_state = "absent"
    if proposal_records or proposal_index_entries:
        if len(proposal_records) != 1 or len(proposal_index_entries) != 1:
            proposal_state = "ambiguous"
        elif not exact_records:
            proposal_state = "mismatch"
        else:
            proposal_path = str(exact_records[0]["path"])
            index_entry = proposal_index_entries[0]
            if (
                index_entry.get("related_plan") != plan_id
                or index_entry.get("related_task") != task_id
                or index_entry.get("path") != proposal_path
            ):
                proposal_state = "mismatch"
            else:
                proposal_state = "published"

    query_identity = {
        "plan_id": plan_id,
        "task_id": task_id,
        "expected_base_head": expected_base_head,
        "expected_base_tree": expected_base_tree,
    }
    return {
        "expected_base_query": {
            "sha256": semantic_digest(query_identity),
            "result": "present" if recoverable_ids else "absent",
        },
        "recoverable_base_handoff_ids": sorted(recoverable_ids),
        "proposal_state": proposal_state,
    }


def _legacy_recovery_global_snapshot(
    control_root: Path,
    plan_id: str,
    task_id: str,
    expected_base_head: str,
    expected_base_tree: str,
) -> dict[str, Any]:
    """Reconstruct the obsolete revision-11 global-digest snapshot."""

    handoff_root = control_root / ".work-bundle/orchestration/handoff"
    stores: dict[str, dict[str, Any]] = {}
    for status in ("active", "archived"):
        records: list[dict[str, str]] = []
        for path in sorted((handoff_root / "executor" / status).glob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                handoff, _ = _read_structured(path)
            except (OSError, SystemExit, ValueError):
                continue
            related = handoff.get("related") if isinstance(handoff.get("related"), Mapping) else {}
            if related.get("plan") != plan_id or related.get("task") != task_id:
                continue
            records.append(
                {
                    "handoff_id": str(handoff.get("id") or ""),
                    "path": path.relative_to(control_root).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        stores[status] = {
            "store_id": f"executor/{status}",
            "records": records,
            "sha256": semantic_digest(records),
        }

    index_path = handoff_root / "index.jsonl"
    if not index_path.is_file() or index_path.is_symlink():
        raise SystemExit("accepted-result recovery requires the native handoff index")
    index_entries: list[dict[str, Any]] = []
    for number, line in enumerate(index_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise SystemExit(
                f"accepted-result recovery handoff index is invalid at line {number}"
            ) from error
        if not isinstance(entry, dict):
            raise SystemExit(f"accepted-result recovery handoff index is invalid at line {number}")
        if entry.get("related_plan") == plan_id and entry.get("related_task") == task_id:
            index_entries.append(entry)
    index_identity = {
        "index_id": "handoff/index.jsonl",
        "path": index_path.relative_to(control_root).as_posix(),
        "sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "projected_entries_sha256": semantic_digest(index_entries),
    }
    historical_revision = semantic_digest(
        {
            "expected_base_head": expected_base_head,
            "expected_base_tree": expected_base_tree,
            "handoff_stores": stores,
            "handoff_index": index_identity,
        }
    )
    return {
        "queried_historical_revision": historical_revision,
        "handoff_stores": stores,
        "handoff_index": index_identity,
    }


def _valid_recovered_result(
    handoff: Mapping[str, Any], plan_id: str, task_id: str
) -> bool:
    related = handoff.get("related") if isinstance(handoff.get("related"), Mapping) else {}
    result = handoff.get("result") if isinstance(handoff.get("result"), Mapping) else {}
    review = (
        handoff.get("acceptance_review")
        if isinstance(handoff.get("acceptance_review"), Mapping)
        else {}
    )
    reset = review.get("review_reset") if isinstance(review.get("review_reset"), Mapping) else {}
    evidence = review.get("evidence") if isinstance(review.get("evidence"), Mapping) else {}
    reviewer = review.get("reviewer") if isinstance(review.get("reviewer"), Mapping) else {}
    identity = review.get("target_identity") if isinstance(review.get("target_identity"), Mapping) else {}
    if (
        handoff.get("type") != "executor-result"
        or related.get("plan") != plan_id
        or related.get("task") != task_id
        or result.get("state") != "completed"
        or review.get("verdict") != "accept"
        or review.get("review_mode") != "initial"
        or review.get("review_target_kind") != "task"
        or review.get("reviewer_independent") is not True
        or review.get("repair_frontier") is not None
        or reset.get("reason_class") != "authority"
        or evidence.get("unavailable_evidence") != []
        or reviewer.get("capability") != "judgment"
        or identity.get("artifact_id") != task_id
        or review.get("reviewed_head") != identity.get("revision")
    ):
        return False
    try:
        from review_runtime import ReviewContractError, validate_task_acceptance_review

        validate_task_acceptance_review(review)
        owner = normalize_subagent_provenance(
            handoff.get("delegation_evidence")
            if isinstance(handoff.get("delegation_evidence"), Mapping)
            else None
        )
    except (ReviewContractError, OwnershipBlocker, KeyError, TypeError, ValueError):
        return False
    return reviewer.get("agent_id") != owner.get("agent_id")


def _write_query_scoped_recovery_receipt(
    control_root: Path,
    plan_id: str,
    task_id: str,
    binding: Mapping[str, Any],
    binding_path: Path,
    expected_base_head: str,
    expected_base_tree: str,
    proposed_handoff_id: str,
    proposed_review_id: str,
    final_head: str,
    final_tree: str,
    expected_base_query: Mapping[str, Any],
) -> dict[str, str]:
    baseline = binding.get("baseline") if isinstance(binding.get("baseline"), Mapping) else {}
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    receipt_id = (
        f"accepted-result-recovery-{task_id}-"
        f"{str(expected_base_query['sha256'])[:12]}-"
        f"{hashlib.sha256(observed_at.encode()).hexdigest()[:12]}"
    )
    receipt = {
        "receipt_id": receipt_id,
        "schema": RECOVERY_RECEIPT_SCHEMA,
        "plan_id": plan_id,
        "task_id": task_id,
        "binding_id": str((binding.get("ownership") or {}).get("binding_id") or ""),
        "binding_sha256": hashlib.sha256(binding_path.read_bytes()).hexdigest(),
        "baseline_head": str(baseline.get("head") or ""),
        "baseline_tree": str(baseline.get("tree") or ""),
        "expected_base_head": expected_base_head,
        "expected_base_tree": expected_base_tree,
        "expected_base_query": dict(expected_base_query),
        "proposed_recovered_result": {
            "handoff_id": proposed_handoff_id,
            "review_id": proposed_review_id,
            "final_head": final_head,
            "final_tree": final_tree,
        },
        "observed_at": observed_at,
        "freshness": "current_validation_attempt",
    }
    path = _recovery_receipt_path(control_root, plan_id, task_id, receipt_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "receipt_id": receipt_id,
        "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def create_accepted_base_absence_receipt(
    control_root: Path,
    plan_id: str,
    task_id: str,
    expected_base_head: str,
    expected_base_tree: str,
    proposed_handoff_id: str,
    proposed_review_id: str,
    final_head: str,
    final_tree: str,
) -> dict[str, str]:
    """Persist helper-observed proof that no native accepted-result base survives."""

    control_root = control_root.expanduser().resolve()
    binding_path = _binding_path(control_root, plan_id, task_id)
    binding = load_task_execution_binding(control_root, plan_id, task_id)
    baseline = binding.get("baseline") if isinstance(binding.get("baseline"), Mapping) else {}
    baseline_head = str(baseline.get("head") or "")
    baseline_tree = str(baseline.get("tree") or "")
    if not baseline_head or not baseline_tree:
        raise SystemExit("accepted-result recovery requires the original one-time task baseline")
    if not SAFE_ID_RE.fullmatch(proposed_handoff_id) or not SAFE_ID_RE.fullmatch(proposed_review_id):
        raise SystemExit("accepted-result recovery proposed identity is unsafe")
    execution_root = Path(str(binding.get("execution_path") or "")).resolve()
    resolved_expected_head = _resolve_commit(execution_root, expected_base_head)
    resolved_expected_tree = _git(
        execution_root, "rev-parse", f"{resolved_expected_head}^{{tree}}"
    ).strip()
    if resolved_expected_tree != expected_base_tree:
        raise SystemExit("accepted-result recovery expected base Git identity is mismatched")
    resolved_final_head = _resolve_commit(execution_root, final_head)
    resolved_final_tree = _git(execution_root, "rev-parse", f"{resolved_final_head}^{{tree}}").strip()
    if resolved_final_tree != final_tree:
        raise SystemExit("accepted-result recovery proposed final Git identity is mismatched")
    snapshot = _accepted_base_query_snapshot(
        control_root,
        plan_id,
        task_id,
        resolved_expected_head,
        resolved_expected_tree,
        proposed_handoff_id,
        proposed_review_id,
        resolved_final_head,
        resolved_final_tree,
    )
    if snapshot["recoverable_base_handoff_ids"]:
        raise SystemExit("accepted-result recovery rejected: recoverable accepted base handoff exists")
    if snapshot["proposal_state"] != "absent":
        raise SystemExit("accepted-result recovery rejected: proposed result already exists or is ambiguous")
    return _write_query_scoped_recovery_receipt(
        control_root,
        plan_id,
        task_id,
        binding,
        binding_path,
        resolved_expected_head,
        resolved_expected_tree,
        proposed_handoff_id,
        proposed_review_id,
        resolved_final_head,
        resolved_final_tree,
        snapshot["expected_base_query"],
    )


def adopt_existing_recovered_result(
    control_root: Path,
    plan_id: str,
    task_id: str,
    expected_base_head: str,
    expected_base_tree: str,
    handoff_id: str,
    handoff_sha256: str,
    review_id: str,
    final_head: str,
    final_tree: str,
    prior_receipt_reference: object,
) -> dict[str, str]:
    """Adopt one already-published result whose rev11 receipt only globally staled."""

    control_root = control_root.expanduser().resolve()
    if not isinstance(prior_receipt_reference, Mapping) or set(prior_receipt_reference) != {
        "receipt_id", "receipt_sha256"
    }:
        raise SystemExit("post-publication adoption prior receipt reference is invalid")
    if not SAFE_ID_RE.fullmatch(handoff_id) or not SAFE_ID_RE.fullmatch(review_id):
        raise SystemExit("post-publication adoption proposed identity is unsafe")

    binding_path = _binding_path(control_root, plan_id, task_id)
    binding = load_task_execution_binding(control_root, plan_id, task_id)
    baseline = binding.get("baseline") if isinstance(binding.get("baseline"), Mapping) else {}
    binding_id = str((binding.get("ownership") or {}).get("binding_id") or "")
    binding_sha256 = hashlib.sha256(binding_path.read_bytes()).hexdigest()
    execution_root = Path(str(binding.get("execution_path") or "")).resolve()
    resolved_expected_head = _resolve_commit(execution_root, expected_base_head)
    resolved_expected_tree = _git(
        execution_root, "rev-parse", f"{resolved_expected_head}^{{tree}}"
    ).strip()
    if resolved_expected_tree != expected_base_tree:
        raise SystemExit("post-publication adoption expected base Git identity is mismatched")
    resolved_final_head = _resolve_commit(execution_root, final_head)
    resolved_final_tree = _git(
        execution_root, "rev-parse", f"{resolved_final_head}^{{tree}}"
    ).strip()
    if resolved_final_tree != final_tree:
        raise SystemExit("post-publication adoption final Git identity is mismatched")

    prior_receipt_id = str(prior_receipt_reference["receipt_id"])
    prior_path = _recovery_receipt_path(control_root, plan_id, task_id, prior_receipt_id)
    if not prior_path.is_file() or prior_path.is_symlink():
        raise SystemExit("post-publication adoption prior receipt is missing")
    if hashlib.sha256(prior_path.read_bytes()).hexdigest() != str(
        prior_receipt_reference["receipt_sha256"]
    ):
        raise SystemExit("post-publication adoption prior receipt digest is stale")
    try:
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("post-publication adoption prior receipt is invalid") from error
    if not isinstance(prior, dict) or set(prior) != LEGACY_RECOVERY_RECEIPT_KEYS:
        raise SystemExit("post-publication adoption requires the closed revision-11 receipt schema")
    if (
        prior.get("receipt_id") != prior_receipt_id
        or prior.get("schema") != RECOVERY_RECEIPT_SCHEMA
        or prior.get("plan_id") != plan_id
        or prior.get("task_id") != task_id
        or prior.get("binding_id") != binding_id
        or prior.get("binding_sha256") != binding_sha256
        or prior.get("baseline_head") != baseline.get("head")
        or prior.get("baseline_tree") != baseline.get("tree")
        or prior.get("expected_base_head") != resolved_expected_head
        or prior.get("expected_base_tree") != resolved_expected_tree
        or prior.get("absence_result") != "accepted_base_absent"
        or prior.get("freshness") != "current_validation_attempt"
        or not isinstance(prior.get("observed_at"), str)
    ):
        raise SystemExit("post-publication adoption prior receipt has a non-global defect")

    stores = prior.get("handoff_stores")
    index_identity = prior.get("handoff_index")
    if not isinstance(stores, Mapping) or set(stores) != {"active", "archived"}:
        raise SystemExit("post-publication adoption prior receipt stores are invalid")
    recorded_ids: set[str] = set()
    for status in ("active", "archived"):
        store = stores[status]
        if not isinstance(store, Mapping) or set(store) != {"store_id", "records", "sha256"}:
            raise SystemExit("post-publication adoption prior receipt store is invalid")
        records = store.get("records")
        if (
            store.get("store_id") != f"executor/{status}"
            or not isinstance(records, list)
            or store.get("sha256") != semantic_digest(records)
        ):
            raise SystemExit("post-publication adoption prior receipt store digest is invalid")
        for record in records:
            if not isinstance(record, Mapping) or set(record) != {"handoff_id", "path", "sha256"}:
                raise SystemExit("post-publication adoption prior receipt record is invalid")
            recorded_ids.add(str(record.get("handoff_id") or ""))
            record_path = (control_root / str(record.get("path") or "")).resolve()
            try:
                record_path.relative_to(control_root)
            except ValueError as error:
                raise SystemExit("post-publication adoption prior receipt record path is unsafe") from error
            if (
                not record_path.is_file()
                or record_path.is_symlink()
                or hashlib.sha256(record_path.read_bytes()).hexdigest() != record.get("sha256")
            ):
                raise SystemExit("post-publication adoption prior receipt record is stale")
            try:
                recorded_handoff, _ = _read_structured(record_path)
            except (OSError, SystemExit, ValueError) as error:
                raise SystemExit("post-publication adoption prior receipt record is invalid") from error
            if _is_recoverable_accepted_base(
                recorded_handoff,
                plan_id,
                task_id,
                resolved_expected_head,
                resolved_expected_tree,
            ):
                raise SystemExit("post-publication adoption prior expected-base query was not absent")
    if handoff_id in recorded_ids:
        raise SystemExit("post-publication adoption candidate was already present in the prior receipt")
    if not isinstance(index_identity, Mapping) or set(index_identity) != {
        "index_id", "path", "sha256", "projected_entries_sha256"
    }:
        raise SystemExit("post-publication adoption prior receipt index is invalid")
    if (
        index_identity.get("index_id") != "handoff/index.jsonl"
        or index_identity.get("path") != ".work-bundle/orchestration/handoff/index.jsonl"
        or any(
            not re.fullmatch(r"[0-9a-f]{64}", str(index_identity.get(field) or ""))
            for field in ("sha256", "projected_entries_sha256")
        )
    ):
        raise SystemExit("post-publication adoption prior receipt index digest is invalid")
    prior_revision = semantic_digest(
        {
            "expected_base_head": resolved_expected_head,
            "expected_base_tree": resolved_expected_tree,
            "handoff_stores": stores,
            "handoff_index": index_identity,
        }
    )
    if prior.get("queried_historical_revision") != prior_revision:
        raise SystemExit("post-publication adoption prior receipt historical revision is invalid")
    expected_receipt_prefix = f"accepted-result-recovery-{task_id}-{prior_revision[:12]}-"
    observed_suffix = hashlib.sha256(str(prior["observed_at"]).encode()).hexdigest()[:12]
    if prior_receipt_id != f"{expected_receipt_prefix}{observed_suffix}":
        raise SystemExit("post-publication adoption prior receipt identity is invalid")

    snapshot = _accepted_base_query_snapshot(
        control_root,
        plan_id,
        task_id,
        resolved_expected_head,
        resolved_expected_tree,
        handoff_id,
        review_id,
        resolved_final_head,
        resolved_final_tree,
    )
    if snapshot["recoverable_base_handoff_ids"]:
        raise SystemExit("post-publication adoption rejected: recoverable accepted base exists")
    if snapshot["proposal_state"] != "published":
        raise SystemExit("post-publication adoption candidate is missing, mismatched, or ambiguous")

    handoff_root = control_root / ".work-bundle/orchestration/handoff"
    _, candidate = _exact_handoff_reference(
        handoff_root, {"handoff_id": handoff_id, "handoff_sha256": handoff_sha256}
    )
    if not _valid_recovered_result(candidate, plan_id, task_id):
        raise SystemExit("post-publication adoption candidate is not a valid recovered result")
    for path in sorted(handoff_root.glob("executor/*/*")):
        if not path.is_file() or path.is_symlink():
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() == handoff_sha256:
            continue
        try:
            other, _ = _read_structured(path)
        except (OSError, SystemExit, ValueError):
            continue
        if _valid_recovered_result(other, plan_id, task_id):
            raise SystemExit("post-publication adoption rejected: valid competing recovered result exists")

    current_legacy = _legacy_recovery_global_snapshot(
        control_root,
        plan_id,
        task_id,
        resolved_expected_head,
        resolved_expected_tree,
    )
    if all(prior.get(field) == current_legacy[field] for field in current_legacy):
        raise SystemExit("post-publication adoption prior receipt is not globally stale")
    return _write_query_scoped_recovery_receipt(
        control_root,
        plan_id,
        task_id,
        binding,
        binding_path,
        resolved_expected_head,
        resolved_expected_tree,
        handoff_id,
        review_id,
        resolved_final_head,
        resolved_final_tree,
        snapshot["expected_base_query"],
    )


def validate_accepted_base_absence_receipt(
    control_root: Path,
    plan_id: str,
    task_id: str,
    reference: object,
) -> dict[str, Any]:
    if not isinstance(reference, Mapping) or set(reference) != {"receipt_id", "receipt_sha256"}:
        raise SystemExit("accepted-result recovery receipt reference must use the closed identity shape")
    receipt_id = str(reference["receipt_id"])
    path = _recovery_receipt_path(control_root, plan_id, task_id, receipt_id)
    if not path.is_file() or path.is_symlink():
        raise SystemExit("accepted-result recovery receipt is missing")
    if hashlib.sha256(path.read_bytes()).hexdigest() != str(reference["receipt_sha256"]):
        raise SystemExit("accepted-result recovery receipt is stale")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("accepted-result recovery receipt is invalid") from error
    if not isinstance(receipt, dict) or set(receipt) != RECOVERY_RECEIPT_KEYS:
        raise SystemExit("accepted-result recovery receipt must use the closed schema")
    if (
        receipt.get("receipt_id") != receipt_id
        or receipt.get("schema") != RECOVERY_RECEIPT_SCHEMA
        or receipt.get("plan_id") != plan_id
        or receipt.get("task_id") != task_id
        or receipt.get("freshness") != "current_validation_attempt"
    ):
        raise SystemExit("accepted-result recovery receipt identity is mismatched")
    binding_path = _binding_path(control_root, plan_id, task_id)
    binding = load_task_execution_binding(control_root, plan_id, task_id)
    baseline = binding.get("baseline") if isinstance(binding.get("baseline"), Mapping) else {}
    if (
        receipt.get("binding_id") != (binding.get("ownership") or {}).get("binding_id")
        or receipt.get("binding_sha256") != hashlib.sha256(binding_path.read_bytes()).hexdigest()
        or receipt.get("baseline_head") != baseline.get("head")
        or receipt.get("baseline_tree") != baseline.get("tree")
    ):
        raise SystemExit("accepted-result recovery receipt binding or baseline is stale")
    execution_root = Path(str(binding.get("execution_path") or "")).resolve()
    expected_head = _resolve_commit(execution_root, str(receipt.get("expected_base_head") or ""))
    expected_tree = _git(execution_root, "rev-parse", f"{expected_head}^{{tree}}").strip()
    if receipt.get("expected_base_tree") != expected_tree:
        raise SystemExit("accepted-result recovery receipt expected base identity is stale")
    proposal = receipt.get("proposed_recovered_result")
    if not isinstance(proposal, Mapping) or set(proposal) != {
        "handoff_id", "review_id", "final_head", "final_tree"
    }:
        raise SystemExit("accepted-result recovery receipt proposed result is invalid")
    final_head = _resolve_commit(execution_root, str(proposal.get("final_head") or ""))
    final_tree = _git(execution_root, "rev-parse", f"{final_head}^{{tree}}").strip()
    if proposal.get("final_tree") != final_tree:
        raise SystemExit("accepted-result recovery receipt proposed final identity is stale")
    snapshot = _accepted_base_query_snapshot(
        control_root,
        plan_id,
        task_id,
        expected_head,
        expected_tree,
        str(proposal.get("handoff_id") or ""),
        str(proposal.get("review_id") or ""),
        final_head,
        final_tree,
    )
    if snapshot["recoverable_base_handoff_ids"]:
        raise SystemExit("accepted-result recovery rejected: recoverable accepted base handoff exists")
    if receipt.get("expected_base_query") != snapshot["expected_base_query"]:
        raise SystemExit("accepted-result recovery receipt expected-base query is stale")
    if snapshot["proposal_state"] in {"mismatch", "ambiguous"}:
        raise SystemExit("accepted-result recovery proposed result is mismatched or ambiguous")
    return {**receipt, "proposal_state": snapshot["proposal_state"]}


def _recovered_accepted_dependency_paths(
    task: dict[str, Any],
    execution_root: Path,
    descriptors: list[Mapping[str, object]],
) -> set[str]:
    required_fields = {
        "task_id",
        "execution_baseline_recovery",
        "recovered_result",
        "accepted_result_delta",
        "integrated_base",
        "integrated_head",
    }
    recovery_fields = {
        "binding_id",
        "binding_sha256",
        "baseline_head",
        "baseline_tree",
        "recovery_receipt",
    }
    delta_fields = {
        "expected_base_head",
        "expected_base_tree",
        "final_head",
        "final_tree",
    }
    dependencies = {str(value) for value in _as_list(task.get("depends_on"))}
    plan_id = str(task.get("plan_id") or "")
    workspace = task.get("workspace") if isinstance(task.get("workspace"), dict) else {}
    control_root = Path(str(workspace.get("root") or "")).resolve()
    handoff_root = control_root / ".work-bundle/orchestration/handoff"
    current_head = _resolve_commit(execution_root, "HEAD")
    admitted: set[str] = set()
    seen_dependencies: set[str] = set()
    for descriptor in descriptors:
        if set(descriptor) != required_fields:
            raise SystemExit(
                "accepted_dependency_deltas recovery entries must use the closed runtime identity shape"
            )
        dependency_id = str(descriptor["task_id"])
        if dependency_id not in dependencies:
            raise SystemExit(f"accepted_dependency_deltas names undeclared dependency: {dependency_id}")
        if dependency_id in seen_dependencies:
            raise SystemExit(f"accepted_dependency_deltas duplicates dependency: {dependency_id}")
        seen_dependencies.add(dependency_id)
        recovery = descriptor["execution_baseline_recovery"]
        if not isinstance(recovery, Mapping) or set(recovery) != recovery_fields:
            raise SystemExit("execution_baseline_recovery must use the closed runtime identity shape")

        binding_path = _binding_path(control_root, plan_id, dependency_id)
        binding = load_task_execution_binding(control_root, plan_id, dependency_id)
        baseline = binding.get("baseline") if isinstance(binding.get("baseline"), Mapping) else {}
        binding_id = str((binding.get("ownership") or {}).get("binding_id") or "")
        binding_digest = hashlib.sha256(binding_path.read_bytes()).hexdigest()
        if (
            recovery.get("binding_id") != binding_id
            or recovery.get("binding_sha256") != binding_digest
            or recovery.get("baseline_head") != baseline.get("head")
            or recovery.get("baseline_tree") != baseline.get("tree")
        ):
            raise SystemExit("execution_baseline_recovery binding or original baseline is mismatched")
        receipt = validate_accepted_base_absence_receipt(
            control_root,
            plan_id,
            dependency_id,
            recovery.get("recovery_receipt"),
        )
        if receipt.get("proposal_state") != "published":
            raise SystemExit("accepted-result recovery proposed result is not published and indexed")

        delta = descriptor["accepted_result_delta"]
        if not isinstance(delta, Mapping) or set(delta) != delta_fields:
            raise SystemExit("accepted_result_delta must use the closed runtime identity shape")
        proposal = receipt["proposed_recovered_result"]
        if (
            delta.get("expected_base_head") != receipt.get("expected_base_head")
            or delta.get("expected_base_tree") != receipt.get("expected_base_tree")
            or delta.get("final_head") != proposal.get("final_head")
            or delta.get("final_tree") != proposal.get("final_tree")
        ):
            raise SystemExit("accepted_result_delta is mismatched with the recovery receipt")
        recovered_reference = descriptor["recovered_result"]
        if (
            not isinstance(recovered_reference, Mapping)
            or recovered_reference.get("handoff_id") != proposal.get("handoff_id")
        ):
            raise SystemExit("recovered result is mismatched with the recovery receipt proposal")

        _, recovered = _exact_handoff_reference(handoff_root, recovered_reference)
        related = recovered.get("related") if isinstance(recovered.get("related"), Mapping) else {}
        result = recovered.get("result") if isinstance(recovered.get("result"), Mapping) else {}
        review = (
            recovered.get("acceptance_review")
            if isinstance(recovered.get("acceptance_review"), Mapping)
            else {}
        )
        reset = review.get("review_reset") if isinstance(review.get("review_reset"), Mapping) else {}
        evidence = review.get("evidence") if isinstance(review.get("evidence"), Mapping) else {}
        reviewer = review.get("reviewer") if isinstance(review.get("reviewer"), Mapping) else {}
        identity = review.get("target_identity") if isinstance(review.get("target_identity"), Mapping) else {}
        if (
            related.get("plan") != plan_id
            or related.get("task") != dependency_id
            or result.get("state") != "completed"
            or review.get("verdict") != "accept"
            or review.get("review_mode") != "initial"
            or review.get("review_target_kind") != "task"
            or review.get("reviewer_independent") is not True
            or review.get("repair_frontier") is not None
            or reset.get("reason_class") != "authority"
            or evidence.get("unavailable_evidence") != []
            or reviewer.get("capability") != "judgment"
            or identity.get("artifact_id") != dependency_id
            or review.get("reviewed_head") != identity.get("revision")
            or review.get("review_id") != proposal.get("review_id")
        ):
            raise SystemExit(
                "recovered result requires a fresh complete independent whole-task initial authority review with empty unavailable_evidence"
            )
        try:
            from review_runtime import ReviewContractError, validate_task_acceptance_review

            validate_task_acceptance_review(review)
        except ReviewContractError as error:
            raise SystemExit(f"recovered result task review is invalid: {error}") from error
        try:
            owner = normalize_subagent_provenance(
                recovered.get("delegation_evidence")
                if isinstance(recovered.get("delegation_evidence"), Mapping)
                else None
            )
        except OwnershipBlocker as error:
            raise SystemExit(f"recovered result ownership is invalid: {error}") from error
        if reviewer.get("agent_id") == owner.get("agent_id"):
            raise SystemExit("recovered result reviewer is not independent from the task owner")

        source_base = _resolve_commit(execution_root, str(delta.get("expected_base_head") or ""))
        source_head = _resolve_commit(execution_root, str(delta.get("final_head") or ""))
        source_tree = _git(execution_root, "rev-parse", f"{source_head}^{{tree}}").strip()
        source_base_tree = _git(execution_root, "rev-parse", f"{source_base}^{{tree}}").strip()
        if delta.get("expected_base_tree") != source_base_tree:
            raise SystemExit("accepted_result_delta expected base Git identity is mismatched")
        if delta.get("final_tree") != source_tree or identity.get("source_tree") != source_tree:
            raise SystemExit("recovered result Git identity is mismatched")
        if subprocess.run(
            ["git", "-C", str(execution_root), "merge-base", "--is-ancestor", source_base, source_head],
            capture_output=True,
            check=False,
        ).returncode:
            raise SystemExit("recovered result source chain is non-ancestral")
        integrated_base = _resolve_commit(execution_root, str(descriptor["integrated_base"]))
        integrated_head = _resolve_commit(execution_root, str(descriptor["integrated_head"]))
        if subprocess.run(
            ["git", "-C", str(execution_root), "merge-base", "--is-ancestor", integrated_head, current_head],
            capture_output=True,
            check=False,
        ).returncode:
            raise SystemExit("recovered result integration checkpoint is not current")
        source_diff = _git(execution_root, "diff", "--binary", source_base, source_head, "--")
        integrated_diff = _git(
            execution_root, "diff", "--binary", integrated_base, integrated_head, "--"
        )
        if source_diff != integrated_diff:
            raise SystemExit("recovered result integration checkpoint is mismatched")
        paths = {
            path
            for line in _git(
                execution_root, "diff", "--name-status", source_base, source_head, "--"
            ).splitlines()
            for path in _paths_from_name_status(line)
        }
        if paths and _git(
            execution_root, "diff", "--name-only", integrated_head, "--", *sorted(paths)
        ).strip():
            raise SystemExit("recovered dependency path changed after integration")
        admitted.update(paths)
    return admitted


def _cumulative_accepted_dependency_paths(
    task: dict[str, Any],
    execution_root: Path,
    descriptors: list[Mapping[str, object]],
) -> set[str]:
    required_fields = {
        "task_id", "accepted_result_base", "review_chain", "integrated_base", "integrated_head"
    }
    dependencies = {str(value) for value in _as_list(task.get("depends_on"))}
    plan_id = str(task.get("plan_id") or "")
    workspace = task.get("workspace") if isinstance(task.get("workspace"), dict) else {}
    handoff_root = (
        Path(str(workspace.get("root") or "")).resolve()
        / ".work-bundle/orchestration/handoff"
    )
    current_head = _resolve_commit(execution_root, "HEAD")
    admitted: set[str] = set()
    seen_dependencies: set[str] = set()
    for descriptor in descriptors:
        if set(descriptor) != required_fields:
            raise SystemExit(
                "accepted_dependency_deltas cumulative entries must use the closed runtime identity shape"
            )
        dependency_id = str(descriptor["task_id"])
        if dependency_id not in dependencies:
            raise SystemExit(f"accepted_dependency_deltas names undeclared dependency: {dependency_id}")
        if dependency_id in seen_dependencies:
            raise SystemExit(f"accepted_dependency_deltas duplicates dependency: {dependency_id}")
        seen_dependencies.add(dependency_id)
        chain_references = descriptor["review_chain"]
        if (not isinstance(chain_references, list) or not chain_references
                or any(not isinstance(item, Mapping) for item in chain_references)):
            raise SystemExit("accepted dependency review_chain must be non-empty and exact")
        reference_ids = [str(item.get("handoff_id") or "") for item in chain_references]
        if len(reference_ids) != len(set(reference_ids)):
            raise SystemExit("accepted dependency review_chain cannot contain duplicated handoffs")

        _, base_handoff = _exact_handoff_reference(
            handoff_root, descriptor["accepted_result_base"]
        )
        base_related = base_handoff.get("related") if isinstance(base_handoff.get("related"), dict) else {}
        base_result = base_handoff.get("result") if isinstance(base_handoff.get("result"), dict) else {}
        base_review = base_handoff.get("acceptance_review") if isinstance(base_handoff.get("acceptance_review"), dict) else {}
        if (base_related.get("plan") != plan_id or base_related.get("task") != dependency_id
                or base_result.get("state") != "completed" or base_review.get("verdict") != "accept"):
            raise SystemExit("accepted dependency result base is not an accepted plan/task result")

        chain: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for reference in chain_references:
            _, handoff = _exact_handoff_reference(handoff_root, reference)
            related = handoff.get("related") if isinstance(handoff.get("related"), dict) else {}
            result = handoff.get("result") if isinstance(handoff.get("result"), dict) else {}
            review = handoff.get("acceptance_review") if isinstance(handoff.get("acceptance_review"), dict) else {}
            if related.get("plan") != plan_id or related.get("task") != dependency_id:
                raise SystemExit("accepted dependency review_chain plan/task identity is mismatched")
            chain.append((handoff, result, review))

        try:
            from review_runtime import (
                ReviewContractError,
                review_evidence_identity,
                validate_task_acceptance_review,
            )
            validate_task_acceptance_review(base_review)
            base_identity = base_review.get("target_identity")
            if (not isinstance(base_identity, Mapping)
                    or base_identity.get("artifact_id") != dependency_id
                    or base_review.get("reviewed_head") != base_identity.get("revision")):
                raise SystemExit("accepted dependency result base identity is mismatched")
            previous_review = base_review
            seen_review_ids = {str(base_review.get("review_id") or "")}
            for _, result, review in chain:
                # The bounded previous_review embedded in each chain link lets the
                # native sequence validator enforce repair continuity and material-
                # change reset isolation without reacquiring older history.
                validate_task_acceptance_review(review)
                review_id = str(review.get("review_id") or "")
                identity = review.get("target_identity")
                if (review_id in seen_review_ids or not isinstance(identity, Mapping)
                        or identity.get("artifact_id") != dependency_id
                        or review.get("reviewed_head") != identity.get("revision")):
                    raise SystemExit("accepted dependency review_chain review identity is duplicated or mismatched")
                seen_review_ids.add(review_id)
                revision = _resolve_commit(execution_root, str(identity.get("revision") or ""))
                tree = _git(execution_root, "rev-parse", f"{revision}^{{tree}}").strip()
                if tree != identity.get("source_tree"):
                    raise SystemExit("accepted dependency review_chain Git identity is mismatched")
                carried = review.get("previous_review")
                if (not isinstance(carried, Mapping) or "previous_review" in carried
                        or _review_without_history(carried) != _review_without_history(previous_review)):
                    raise SystemExit("accepted dependency review_chain prior review is missing or mismatched")
                mode = review.get("review_mode")
                if mode == "repair":
                    frontier = review.get("repair_frontier")
                    if not isinstance(frontier, Mapping):
                        raise SystemExit("accepted dependency review_chain repair frontier is missing")
                    blocking = [
                        str(item.get("finding_id"))
                        for item in _as_list(previous_review.get("findings"))
                        if isinstance(item, Mapping) and item.get("severity") == "blocking"
                    ]
                    if (frontier.get("prior_review_id") != previous_review.get("review_id")
                            or frontier.get("previous_reviewed_identity") != previous_review.get("target_identity")
                            or frontier.get("repaired_identity") != review.get("target_identity")
                            or list(frontier.get("blocking_finding_ids") or []) != blocking
                            or frontier.get("frozen_evidence_reference") != review_evidence_identity(previous_review)):
                        raise SystemExit("accepted dependency review_chain repair continuity is mismatched")
                else:
                    reset = review.get("review_reset")
                    if not isinstance(reset, Mapping) or reset.get("prior_review_id") != previous_review.get("review_id"):
                        raise SystemExit("accepted dependency review_chain initial reset is non-contiguous")
                if review.get("verdict") not in {"repair", "accept"}:
                    raise SystemExit("accepted dependency review_chain contains a blocked review")
                if review.get("verdict") == "accept" and result.get("state") != "completed":
                    raise SystemExit("accepted dependency review_chain accepted result is incomplete")
                previous_review = review
        except ReviewContractError as error:
            raise SystemExit(f"accepted dependency review_chain is invalid: {error}") from error

        _, final_result, final_review = chain[-1]
        if final_review.get("verdict") != "accept" or final_result.get("state") != "completed":
            raise SystemExit("accepted dependency review_chain final result is not accepted")
        base_identity = base_review.get("target_identity")
        final_identity = final_review.get("target_identity")
        if not isinstance(base_identity, Mapping) or not isinstance(final_identity, Mapping):
            raise SystemExit("accepted dependency cumulative result identity is incomplete")
        for identity in (base_identity, final_identity):
            revision = _resolve_commit(execution_root, str(identity.get("revision") or ""))
            tree = _git(execution_root, "rev-parse", f"{revision}^{{tree}}").strip()
            if tree != identity.get("source_tree"):
                raise SystemExit("accepted dependency cumulative Git identity is mismatched")

        final_review_id = str(final_review.get("review_id") or "")
        chain_ids = set(reference_ids)
        successor_edges: list[tuple[str, str]] = []
        for path in sorted(handoff_root.glob("executor/*/*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                candidate, _ = _read_structured(path)
            except (OSError, SystemExit, ValueError):
                continue
            if str(candidate.get("id") or "") in chain_ids:
                continue
            related = candidate.get("related") if isinstance(candidate.get("related"), dict) else {}
            review = candidate.get("acceptance_review") if isinstance(candidate.get("acceptance_review"), dict) else {}
            frontier = review.get("repair_frontier") if isinstance(review.get("repair_frontier"), dict) else {}
            reset = review.get("review_reset") if isinstance(review.get("review_reset"), dict) else {}
            prior_id = frontier.get("prior_review_id") or reset.get("prior_review_id")
            if (related.get("plan") == plan_id and related.get("task") == dependency_id
                    and isinstance(prior_id, str) and prior_id):
                successor_edges.append((prior_id, str(review.get("review_id") or "")))
        reachable = {final_review_id}
        while True:
            additions = {current for prior, current in successor_edges if prior in reachable}
            if additions.issubset(reachable):
                break
            reachable.update(additions)
        if any(prior in reachable for prior, _ in successor_edges):
            raise SystemExit("accepted dependency review_chain terminal result is stale")

        source_base = _resolve_commit(execution_root, str(base_identity.get("revision") or ""))
        source_head = _resolve_commit(execution_root, str(final_identity.get("revision") or ""))
        if subprocess.run(
            ["git", "-C", str(execution_root), "merge-base", "--is-ancestor", source_base, source_head],
            capture_output=True,
            check=False,
        ).returncode:
            raise SystemExit("accepted dependency cumulative source chain is non-ancestral")
        integrated_base = _resolve_commit(execution_root, str(descriptor["integrated_base"]))
        integrated_head = _resolve_commit(execution_root, str(descriptor["integrated_head"]))
        if subprocess.run(
            ["git", "-C", str(execution_root), "merge-base", "--is-ancestor", integrated_head, current_head],
            capture_output=True,
            check=False,
        ).returncode:
            raise SystemExit("accepted dependency cumulative integration checkpoint is not current")
        source_diff = _git(execution_root, "diff", "--binary", source_base, source_head, "--")
        integrated_diff = _git(
            execution_root, "diff", "--binary", integrated_base, integrated_head, "--"
        )
        if source_diff != integrated_diff:
            raise SystemExit("accepted dependency cumulative integration checkpoint is mismatched")
        paths = {
            path
            for line in _git(execution_root, "diff", "--name-status", source_base, source_head, "--").splitlines()
            for path in _paths_from_name_status(line)
        }
        if paths and _git(
            execution_root, "diff", "--name-only", integrated_head, "--", *sorted(paths)
        ).strip():
            raise SystemExit("accepted dependency cumulative path changed after integration")
        admitted.update(paths)
    return admitted


def _accepted_dependency_paths(
    task: dict[str, Any],
    execution_root: Path,
    accepted_dependency_deltas: Iterable[Mapping[str, object]] | None,
) -> set[str]:
    descriptors = list(accepted_dependency_deltas or [])
    if not descriptors:
        return set()
    cumulative_fields = {
        "task_id", "accepted_result_base", "review_chain", "integrated_base", "integrated_head"
    }
    recovery_fields = {
        "task_id", "execution_baseline_recovery", "recovered_result", "accepted_result_delta",
        "integrated_base", "integrated_head"
    }
    cumulative = [
        item for item in descriptors if isinstance(item, Mapping) and set(item) == cumulative_fields
    ]
    recovered = [
        item for item in descriptors if isinstance(item, Mapping) and set(item) == recovery_fields
    ]
    if cumulative or recovered:
        if len(cumulative) + len(recovered) != len(descriptors):
            raise SystemExit("accepted_dependency_deltas cannot mix closed and legacy identities")
        dependency_ids = [str(item["task_id"]) for item in [*cumulative, *recovered]]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise SystemExit("accepted_dependency_deltas duplicates dependency")
        return (
            _cumulative_accepted_dependency_paths(task, execution_root, cumulative)
            | _recovered_accepted_dependency_paths(task, execution_root, recovered)
        )
    dependencies = {str(value) for value in _as_list(task.get("depends_on"))}
    plan_id = str(task.get("plan_id") or "")
    workspace = task.get("workspace") if isinstance(task.get("workspace"), dict) else {}
    control_root = Path(str(workspace.get("root") or "")).resolve()
    handoff_root = control_root / ".work-bundle/orchestration/handoff"
    admitted: set[str] = set()
    chain_tail_by_dependency: dict[str, dict[str, Any]] = {}
    chain_by_dependency: dict[str, dict[str, Any]] = {}
    last_checkpoint_by_path: dict[str, tuple[str, str]] = {}
    current_head = _resolve_commit(execution_root, "HEAD")
    required_fields = {
        "task_id", "handoff_id", "handoff_sha256", "integrated_base", "integrated_head"
    }
    for descriptor in descriptors:
        if not isinstance(descriptor, Mapping) or set(descriptor) != required_fields:
            raise SystemExit("accepted_dependency_deltas entries must use the closed runtime identity shape")
        dependency_id = str(descriptor["task_id"])
        handoff_id = str(descriptor["handoff_id"])
        if dependency_id not in dependencies:
            raise SystemExit(f"accepted_dependency_deltas names undeclared dependency: {dependency_id}")
        matches: list[tuple[Path, dict[str, Any]]] = []
        for path in sorted(handoff_root.glob("executor/*/*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                document, _ = _read_structured(path)
            except (OSError, SystemExit, ValueError):
                continue
            if document.get("id") == handoff_id:
                matches.append((path, document))
        if len(matches) != 1:
            raise SystemExit(f"accepted dependency handoff identity is missing or ambiguous: {handoff_id}")
        handoff_path, handoff = matches[0]
        actual_digest = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
        if actual_digest != str(descriptor["handoff_sha256"]):
            raise SystemExit(f"accepted dependency handoff identity is stale: {handoff_id}")
        related = handoff.get("related") if isinstance(handoff.get("related"), dict) else {}
        result = handoff.get("result") if isinstance(handoff.get("result"), dict) else {}
        review = handoff.get("acceptance_review") if isinstance(handoff.get("acceptance_review"), dict) else {}
        frontier = review.get("repair_frontier") if isinstance(review.get("repair_frontier"), dict) else {}
        previous = frontier.get("previous_reviewed_identity") if isinstance(frontier.get("previous_reviewed_identity"), dict) else {}
        repaired = frontier.get("repaired_identity") if isinstance(frontier.get("repaired_identity"), dict) else {}
        if related.get("plan") != plan_id or related.get("task") != dependency_id:
            raise SystemExit(
                f"accepted dependency handoff plan/task identity is mismatched: {handoff_id}"
            )
        if (result.get("state") != "completed" or review.get("verdict") != "accept"
                or review.get("review_mode") != "repair"
                or repaired != review.get("target_identity")):
            raise SystemExit(f"dependency handoff is not an accepted repair result: {handoff_id}")
        source_base = str(previous.get("revision") or "")
        source_head = str(repaired.get("revision") or "")
        integrated_base = _resolve_commit(execution_root, str(descriptor["integrated_base"]))
        integrated_head = _resolve_commit(execution_root, str(descriptor["integrated_head"]))
        if not source_base or not source_head:
            raise SystemExit(f"accepted dependency repair identity is incomplete: {handoff_id}")
        for commit, identity in ((source_base, previous), (source_head, repaired)):
            resolved = _resolve_commit(execution_root, commit)
            tree = _git(execution_root, "rev-parse", f"{resolved}^{{tree}}").strip()
            if tree != identity.get("source_tree"):
                raise SystemExit(f"accepted dependency Git identity is mismatched: {handoff_id}")
        prior_link = chain_tail_by_dependency.get(dependency_id)
        if prior_link is not None:
            if previous != prior_link["repaired_identity"]:
                raise SystemExit(
                    "accepted dependency source chain is not ordered and contiguous: "
                    f"{handoff_id}"
                )
            if integrated_base != prior_link["integrated_head"]:
                raise SystemExit(
                    "accepted dependency integrated chain is non-adjacent: "
                    f"{handoff_id}"
                )
        if subprocess.run(
            ["git", "-C", str(execution_root), "merge-base", "--is-ancestor", integrated_head, current_head],
            capture_output=True,
            check=False,
        ).returncode:
            raise SystemExit(f"accepted dependency integration checkpoint is not current: {handoff_id}")
        source_diff = _git(execution_root, "diff", "--binary", source_base, source_head, "--")
        integrated_diff = _git(
            execution_root, "diff", "--binary", integrated_base, integrated_head, "--"
        )
        if source_diff != integrated_diff:
            raise SystemExit(f"accepted dependency integration checkpoint is mismatched: {handoff_id}")
        paths = {
            path
            for line in _git(execution_root, "diff", "--name-status", source_base, source_head, "--").splitlines()
            for path in _paths_from_name_status(line)
        }
        chain_tail_by_dependency[dependency_id] = {
            "repaired_identity": repaired,
            "integrated_head": integrated_head,
        }
        chain = chain_by_dependency.setdefault(
            dependency_id,
            {
                "first_previous_identity": previous,
                "last_repaired_identity": repaired,
                "accepted_edges": set(),
            },
        )
        chain["last_repaired_identity"] = repaired
        chain["accepted_edges"].add(
            semantic_digest({"previous": previous, "repaired": repaired})
        )
        for path in paths:
            last_checkpoint_by_path[path] = (integrated_head, handoff_id)
    for dependency_id, chain in chain_by_dependency.items():
        for path in sorted(handoff_root.glob("executor/*/*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                candidate, _ = _read_structured(path)
            except (OSError, SystemExit, ValueError):
                continue
            related = candidate.get("related") if isinstance(candidate.get("related"), dict) else {}
            result = candidate.get("result") if isinstance(candidate.get("result"), dict) else {}
            review = candidate.get("acceptance_review") if isinstance(candidate.get("acceptance_review"), dict) else {}
            frontier = review.get("repair_frontier") if isinstance(review.get("repair_frontier"), dict) else {}
            previous = frontier.get("previous_reviewed_identity") if isinstance(frontier.get("previous_reviewed_identity"), dict) else {}
            repaired = frontier.get("repaired_identity") if isinstance(frontier.get("repaired_identity"), dict) else {}
            if (related.get("plan") != plan_id or related.get("task") != dependency_id
                    or result.get("state") != "completed"
                    or review.get("verdict") != "accept" or review.get("review_mode") != "repair"
                    or repaired != review.get("target_identity") or not previous or not repaired):
                continue
            edge = semantic_digest({"previous": previous, "repaired": repaired})
            if edge in chain["accepted_edges"]:
                continue
            if repaired == chain["first_previous_identity"]:
                raise SystemExit(
                    "accepted dependency repair chain is not anchored at its known accepted start: "
                    f"{dependency_id}"
                )
            if previous == chain["last_repaired_identity"]:
                raise SystemExit(
                    "accepted dependency repair chain is incomplete at its known accepted head: "
                    f"{dependency_id}"
                )
    for path, (integrated_head, handoff_id) in last_checkpoint_by_path.items():
        if _git(execution_root, "diff", "--name-only", integrated_head, "--", path).strip():
            raise SystemExit(f"accepted dependency path changed after integration: {handoff_id}")
        admitted.add(path)
    return admitted


def _observe_completed_validation(
    handoff: dict[str, Any],
    task: dict[str, Any],
    required_items: list[dict[str, Any]],
    reported_commands: dict[str, dict[str, Any]] | None,
    *,
    workspace_id: str | None = None,
    execution_id: str | None = None,
    repository_id: str | None = None,
    execution_runtime_root: str | None = None,
    accepted_dependency_deltas: Iterable[Mapping[str, object]] | None = None,
) -> list[dict[str, Any]]:
    if "harness_receipt" in handoff or (
        isinstance(handoff.get("validation"), dict) and "harness_receipt" in handoff["validation"]
    ):
        raise SystemExit("Executor-minted harness_receipt is not independent proof")
    control_root_raw = (task.get("workspace") or {}).get("root") if isinstance(task.get("workspace"), dict) else None
    if not control_root_raw:
        raise SystemExit("Task execution binding is missing harness provenance")
    control_root = Path(str(control_root_raw))
    from review_runtime import require_plan_reviews
    require_plan_reviews(control_root, _find_plan(control_root, str(task["plan_id"]))[0])
    binding = load_task_execution_binding(control_root, str(task["plan_id"]), str(task["task_id"]))
    if workspace_id and str(binding.get("workspace_id") or "") != str(workspace_id):
        raise SystemExit("Task execution binding workspace_id mismatch")
    if execution_id and str(binding.get("execution_id") or "") != str(execution_id):
        raise SystemExit("Task execution binding execution_id mismatch")
    if repository_id and str(binding.get("repository_id") or "") != str(repository_id):
        raise SystemExit("Task execution binding repository_id mismatch")
    if execution_runtime_root and Path(str(binding.get("runtime_root") or "")).resolve() != Path(
        execution_runtime_root
    ).expanduser().resolve():
        raise SystemExit("Task execution binding runtime root mismatch")
    baseline = binding.get("baseline")
    if not isinstance(baseline, dict) or not baseline.get("head"):
        raise SystemExit("Task execution binding is missing harness provenance baseline")
    execution_root = Path(str(binding["execution_path"]))
    try:
        pre_batch = capture_repository_evidence(execution_root)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    observed_items: list[dict[str, Any]] = []
    task_files = task.get("files") if isinstance(task.get("files"), dict) else {}
    accepted_paths = _accepted_dependency_paths(task, execution_root, accepted_dependency_deltas)
    _assert_task_caused_delta_in_write_scope(
        task_caused_paths(baseline, pre_batch, execution_root),
        task_files,
        accepted_dependency_paths=accepted_paths,
    )
    for item in required_items:
        observed = _completion_provenance_module().observe_validation(
            binding, task, item, pre_batch,
            lambda receipt: _observe_validation_item(item, execution_root, task, receipt),
            lambda: capture_repository_evidence(execution_root),
        )
        command = str(item.get("command")).strip()
        reported_item = reported_commands[command] if reported_commands is not None else None
        if reported_item is not None and reported_item.get("result") != observed["result"]:
            raise SystemExit(
                f"Executor result validation for {command} does not match observed {observed['result']}"
            )
        allowed = _acceptable_validation_results(item)
        if observed["result"] not in allowed:
            allowed_text = " or ".join(sorted(allowed))
            raise SystemExit(
                f"Observed validation for {command} must be {allowed_text}; got {observed['result']}"
            )
        observed_items.append(observed)
    try:
        post_batch = capture_repository_evidence(execution_root)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    in_batch = task_caused_paths(pre_batch, post_batch, execution_root)
    if in_batch:
        raise SystemExit(
            "validation-blocked: authoritative validation batch mutated Git-observable state; "
            "rerun the full batch after ordinary task work"
        )
    caused = task_caused_paths(baseline, post_batch, execution_root)
    task_files = task.get("files") if isinstance(task.get("files"), dict) else {}
    _assert_task_caused_delta_in_write_scope(
        caused, task_files, accepted_dependency_paths=accepted_paths
    )
    if binding.get("mutating") is True:
        updated = dict(binding)
        updated["mutating"] = False
        _persist_binding(updated, control_root)
    return observed_items


def _task_evidence_applicability(task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    compiled = task.get("evidence_applicability")
    if compiled is None:
        return task_evidence_applicability(task)
    if not isinstance(compiled, dict):
        raise SystemExit("Task evidence_applicability must be a mapping")
    normalized: dict[str, dict[str, Any]] = {}
    for kind in ("metadata", "repository", "codegraph"):
        item = compiled.get(kind)
        if not isinstance(item, dict) or not isinstance(item.get("required"), bool):
            raise SystemExit(f"Task evidence_applicability.{kind}.required must be boolean")
        reasons = item.get("reasons")
        if not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons):
            raise SystemExit(f"Task evidence_applicability.{kind}.reasons must be a string list")
        normalized[kind] = {"required": item["required"], "reasons": list(reasons)}
    return normalized


def _validated_repository_evidence(handoff: dict[str, Any], metadata_required: bool) -> list[dict[str, Any]]:
    entries = handoff.get("repository")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("Executor result is missing applicable repository evidence")
    validated: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("Executor result repository evidence entries must be mappings")
        root = Path(str(entry.get("root") or ""))
        if not root.is_absolute():
            raise SystemExit("Executor result repository evidence root must be absolute")
        if entry.get("target_kind") not in {"git-backed", "local-project"}:
            raise SystemExit("Executor result repository evidence target_kind is invalid")
        if entry.get("preflight_kind") not in {"git-clean-worktree", "local-project"}:
            raise SystemExit("Executor result repository evidence preflight_kind is invalid")
        if entry.get("baseline") not in {"initial", "accepted-handoff"}:
            raise SystemExit("Executor result repository evidence baseline is invalid")
        if entry.get("status") not in {"clean", "blocked"}:
            raise SystemExit("Executor result repository evidence status is invalid")
        if metadata_required:
            metadata = entry.get("metadata")
            required_fields = {
                "repository_id",
                "expected_branch",
                "actual_branch",
                "branch_status",
                "expected_commit",
                "actual_commit",
                "commit_status",
                "baseline_status",
            }
            if not isinstance(metadata, dict) or not required_fields.issubset(metadata):
                raise SystemExit("Executor result repository metadata evidence is missing required fields")
        validated.append(entry)
    return validated


def _validated_codegraph_evidence(
    handoff: dict[str, Any], repository_entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    entries = handoff.get("codegraph")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("Executor result is missing applicable CodeGraph evidence")
    repository_roots = {str(Path(str(entry["root"])).resolve()) for entry in repository_entries}
    validated: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("Executor result CodeGraph evidence entries must be mappings")
        root = Path(str(entry.get("root") or ""))
        if not root.is_absolute():
            raise SystemExit("Executor result CodeGraph evidence root must be absolute")
        if repository_roots and str(root.resolve()) not in repository_roots:
            raise SystemExit("Executor result CodeGraph evidence root has no matching repository evidence")
        applicable = entry.get("applicable")
        up_to_date = entry.get("up_to_date")
        reason = entry.get("reason")
        if not isinstance(applicable, bool) or not isinstance(up_to_date, bool):
            raise SystemExit("Executor result CodeGraph applicable and up_to_date must be boolean")
        if applicable:
            if not up_to_date or reason not in {None, ""}:
                raise SystemExit("Applicable CodeGraph evidence must be up_to_date without a failure reason")
        elif up_to_date or reason != "no-index":
            raise SystemExit("Non-applicable CodeGraph evidence must be explicit no-index")
        validated.append(entry)
    return validated


def _observe_repository_and_codegraph_evidence(
    task: dict[str, Any],
    repository_entries: list[dict[str, Any]],
    codegraph_entries: list[dict[str, Any]],
    *,
    codegraph_required: bool,
    accepted_dependency_deltas: Iterable[Mapping[str, object]] | None = None,
) -> None:
    workspace = task.get("workspace") if isinstance(task.get("workspace"), dict) else {}
    control_root_raw = workspace.get("root")
    if not control_root_raw:
        raise SystemExit("Task execution binding is missing harness provenance")
    binding = load_task_execution_binding(
        Path(str(control_root_raw)), str(task["plan_id"]), str(task["task_id"])
    )
    execution_root = Path(str(binding["execution_path"])).resolve()
    repository = next(
        (entry for entry in repository_entries if Path(str(entry["root"])).resolve() == execution_root),
        None,
    )
    if repository is None:
        raise SystemExit("Executor repository evidence does not match the helper-observed execution binding")
    try:
        observed_repository = capture_repository_evidence(execution_root)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    baseline = binding.get("baseline")
    if not isinstance(baseline, dict) or not baseline.get("head"):
        raise SystemExit("Task execution binding is missing harness provenance baseline")
    caused = task_caused_paths(baseline, observed_repository, execution_root)
    task_files = task.get("files") if isinstance(task.get("files"), dict) else {}
    _assert_task_caused_delta_in_write_scope(
        caused,
        task_files,
        accepted_dependency_paths=_accepted_dependency_paths(
            task, execution_root, accepted_dependency_deltas
        ),
    )

    metadata = repository.get("metadata")
    if isinstance(metadata, dict):
        branch = subprocess.run(
            ["git", "-C", str(execution_root), "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
        )
        if branch.returncode != 0:
            raise SystemExit("Helper-observed repository branch identity is unavailable")
        actual_branch = branch.stdout.strip()
        actual_commit = str(observed_repository.get("head") or "")
        if metadata.get("actual_branch") != actual_branch:
            raise SystemExit("Executor repository branch does not match helper-observed identity")
        if metadata.get("actual_commit") != actual_commit:
            raise SystemExit("Executor repository commit does not match helper-observed identity")
        expected_branch = metadata.get("expected_branch")
        expected_commit = metadata.get("expected_commit")
        observed_branch_status = (
            "not-applicable" if not expected_branch else "matched" if expected_branch == actual_branch else "mismatch"
        )
        observed_commit_status = (
            "not-applicable" if not expected_commit else "matched" if expected_commit == actual_commit else "stale"
        )
        if metadata.get("branch_status") != observed_branch_status:
            raise SystemExit("Executor repository branch status contradicts helper observation")
        if metadata.get("commit_status") != observed_commit_status:
            raise SystemExit("Executor repository commit status contradicts helper observation")
    if not codegraph_required:
        return
    codegraph = next(
        (entry for entry in codegraph_entries if Path(str(entry["root"])).resolve() == execution_root),
        None,
    )
    if codegraph is None:
        raise SystemExit("Executor CodeGraph evidence does not match the helper-observed execution binding")
    marker_exists = (execution_root / ".codegraph").is_dir()
    if marker_exists and codegraph.get("applicable") is not True:
        raise SystemExit("Helper-observed CodeGraph marker contradicts executor no-index evidence")
    if not marker_exists and (
        codegraph.get("applicable") is not False or codegraph.get("reason") != "no-index"
    ):
        raise SystemExit("Helper-observed missing CodeGraph marker requires explicit no-index evidence")
    if marker_exists:
        try:
            status = subprocess.run(
                ["codegraph", "status", "--json", str(execution_root)],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise SystemExit("Helper-observed CodeGraph status is unavailable") from error
        if status.returncode != 0:
            raise SystemExit("Helper-observed CodeGraph status is unavailable")
        try:
            observed_codegraph = json.loads(status.stdout)
        except json.JSONDecodeError as error:
            raise SystemExit("Helper-observed CodeGraph status is malformed") from error
        pending = observed_codegraph.get("pendingChanges")
        index = observed_codegraph.get("index")
        up_to_date = (
            observed_codegraph.get("initialized") is True
            and Path(str(observed_codegraph.get("projectPath") or "")).resolve() == execution_root
            and isinstance(pending, dict)
            and all(pending.get(kind) == 0 for kind in ("added", "modified", "removed"))
            and observed_codegraph.get("worktreeMismatch") is None
            and isinstance(index, dict)
            and index.get("reindexRecommended") is False
        )
        if codegraph.get("up_to_date") is not up_to_date:
            raise SystemExit("Executor CodeGraph up_to_date claim contradicts helper-observed status")


def validate_executor_result_for_task(
    handoff: dict[str, Any],
    task: dict[str, Any],
    *,
    observe: bool = False,
    workspace_id: str | None = None,
    execution_id: str | None = None,
    repository_id: str | None = None,
    execution_runtime_root: str | None = None,
    mutation_events: Iterable[Mapping[str, object]] | None = None,
    accepted_dependency_deltas: Iterable[Mapping[str, object]] | None = None,
    prior_ownership: Mapping[str, Mapping[str, object]] | None = None,
    repair_continuity: Mapping[str, Mapping[str, object] | RepairContinuity] | None = None,
    authorized_replacements: Iterable[str] | None = None,
) -> dict[str, Any]:
    if handoff.get("type") != "executor-result":
        raise SystemExit("Handoff is not executor-result")
    for field in FORBIDDEN_EXECUTOR_RESULT_FIELDS:
        if field in handoff:
            raise SystemExit(f"Executor result contains forbidden field {field}")
    task_id = str(task.get("task_id") or "")
    plan_id = str(task.get("plan_id") or "")
    if not task_id or not plan_id:
        raise SystemExit("Task brief is missing task_id or plan_id")
    _assert_task_handoff_identity(handoff, task_id, plan_id)
    result = handoff.get("result")
    if not isinstance(result, dict) or result.get("state") not in VALID_RESULT_STATES:
        raise SystemExit("Executor result state must be completed, blocked, partial, or failed")
    state = str(result["state"])
    unresolved = _as_list(handoff.get("unresolved"))
    if state == "completed" and unresolved:
        raise SystemExit("Executor result completed state cannot include unresolved blockers")
    task_files = task.get("files") if isinstance(task.get("files"), dict) else {}
    accepted_authority_paths = [
        str(value) for value in [*_as_list(task_files.get("read")), *_as_list(task_files.get("write"))]
    ]
    truth_basis = task.get("truth_basis") if isinstance(task.get("truth_basis"), dict) else {}
    knowledge_disposition = _validated_knowledge_disposition(
        handoff,
        list(task.get("source_ids", [])),
        accepted_authority_paths,
        _allocated_decision_aliases(truth_basis),
    )
    if state in {"completed", "partial"}:
        _assert_task_fit_check(handoff, task_id, state)
        _assert_changed_paths_in_write_scope(handoff, task_files)
    acceptance_review_sequence = _assert_handoff_review_matches_task(handoff, task, state)
    required_items = [
        item
        for item in _as_list(task.get("validation"))
        if isinstance(item, dict) and item.get("command")
    ]
    observed_validation = None
    evidence_closure = None
    reported_commands: dict[str, dict[str, Any]] = {}
    if state == "completed" and required_items:
        reported = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else {}
        reported_commands = {
            str(item.get("command", "")).strip(): item
            for item in _as_list(reported.get("commands"))
            if isinstance(item, dict)
        }
        for item in required_items:
            command = str(item.get("command")).strip()
            if command not in reported_commands:
                raise SystemExit(f"Executor result is missing fresh required validation: {command}")
            reported_item = reported_commands[command]
            compiled_kind = str(item.get("kind") or "").strip().lower()
            if compiled_kind == "legacy-untyped":
                raise SystemExit("Untyped validation item is legacy-untyped")
            if compiled_kind == "inspection":
                mechanism = str(item.get("mechanism") or "").strip()
                reported_mechanism = str(reported_item.get("mechanism") or "").strip()
                if not mechanism or reported_mechanism != mechanism:
                    raise SystemExit(f"Executor result is missing inspection mechanism: {mechanism}")
            allowed = _acceptable_validation_results(item)
            result_value = reported_item.get("result")
            if result_value not in allowed:
                allowed_text = " or ".join(sorted(allowed))
                raise SystemExit(
                    f"Executor result validation for {command} must be {allowed_text}; got {result_value}"
                )
    capability = task.get("evidence_capability") if isinstance(task.get("evidence_capability"), dict) else {}
    if state == "completed" and capability.get("result") == "mapped":
        if not observe:
            raise SystemExit(
                "evidence-closure-blocked: completed mapped invariants require independent harness observation"
            )
    else:
        evidence_closure = _validate_evidence_closure(
            handoff, task, state, reported_commands, None
        )

    evidence_applicability = _task_evidence_applicability(task)
    repository_entries: list[dict[str, Any]] = []
    codegraph_entries: list[dict[str, Any]] = []
    if evidence_applicability["repository"]["required"]:
        repository_entries = _validated_repository_evidence(
            handoff, evidence_applicability["metadata"]["required"]
        )
    elif evidence_applicability["metadata"]["required"]:
        repository_entries = _validated_repository_evidence(handoff, True)
    if evidence_applicability["codegraph"]["required"]:
        codegraph_entries = _validated_codegraph_evidence(handoff, repository_entries)
    if observe and (repository_entries or codegraph_entries):
        _observe_repository_and_codegraph_evidence(
            task,
                repository_entries,
                codegraph_entries,
                codegraph_required=evidence_applicability["codegraph"]["required"],
                accepted_dependency_deltas=accepted_dependency_deltas,
            )

    if state == "completed" and required_items and observe:
        observed_validation = _observe_completed_validation(
            handoff,
            task,
            required_items,
            reported_commands,
            workspace_id=workspace_id,
            execution_id=execution_id,
            repository_id=repository_id,
            execution_runtime_root=execution_runtime_root,
            accepted_dependency_deltas=accepted_dependency_deltas,
        )
        evidence_closure = _validate_evidence_closure(
            handoff, task, state, reported_commands, observed_validation
        )
    if state == "completed" and capability.get("result") == "mapped":
        if observed_validation is None or not isinstance(evidence_closure, dict) or evidence_closure.get("result") != "passed":
            raise SystemExit(
                "evidence-closure-blocked: completed mapped invariants require produced harness observations and passed evidence closure"
            )
    task_ownership = None
    if state == "completed":
        if mutation_events is None:
            raise AcceptanceOwnershipError(
                "review-blocked: completed task requires harness-owned mutation_events evidence"
            )
        runtime_mutation_events = list(mutation_events)
        if any(not isinstance(event, Mapping) for event in runtime_mutation_events):
            raise AcceptanceOwnershipError("Runtime mutation_events must contain mappings")
        fit = handoff.get("task_fit_check") if isinstance(handoff.get("task_fit_check"), dict) else {}
        operation = "repair" if fit.get("result") == "repaired" else "implementation"
        try:
            task_ownership = validate_task_acceptance_ownership(
                delegation_evidence=(
                    handoff.get("delegation_evidence")
                    if isinstance(handoff.get("delegation_evidence"), dict)
                    else None
                ),
                mutation_events=runtime_mutation_events,
                write_scope=_as_list(task_files.get("write")),
                validations_passed=True,
                operation=operation,
            )
            if operation == "repair" and acceptance_review_sequence != "initial-reset":
                _validate_repair_acceptance_continuity(
                    task=task,
                    handoff=handoff,
                    current_ownership=task_ownership,
                    prior_ownership=prior_ownership,
                    repair_continuity=repair_continuity,
                    authorized_replacements=authorized_replacements,
                )
        except OwnershipBlocker as error:
            raise AcceptanceOwnershipError(str(error)) from error
    return {
        "knowledge_disposition": knowledge_disposition,
        "unresolved": unresolved,
        "result_state": state,
        "evidence_applicability": evidence_applicability,
        "evidence_closure": evidence_closure,
        **({"task_ownership": task_ownership} if task_ownership is not None else {}),
        **({"observed_validation": observed_validation} if observed_validation is not None else {}),
    }


def _validate_repair_acceptance_continuity(
    *,
    task: Mapping[str, object],
    handoff: Mapping[str, object],
    current_ownership: Mapping[str, object],
    prior_ownership: Mapping[str, Mapping[str, object]] | None,
    repair_continuity: Mapping[str, Mapping[str, object] | RepairContinuity] | None,
    authorized_replacements: Iterable[str] | None,
) -> None:
    """Bind repair acceptance to the scheduler's original owner and identities."""

    task_id = str(task.get("task_id") or "")
    if prior_ownership is not None and not isinstance(prior_ownership, Mapping):
        raise OwnershipBlocker("review-blocked", "repair prior_ownership must be a task mapping")
    if repair_continuity is not None and not isinstance(repair_continuity, Mapping):
        raise OwnershipBlocker("review-blocked", "repair_continuity must be a task mapping")
    previous_value = (prior_ownership or {}).get(task_id)
    continuity_value = (repair_continuity or {}).get(task_id)
    if previous_value is None:
        raise OwnershipBlocker("review-blocked", f"{task_id} repair lacks prior owner")
    if continuity_value is None:
        raise OwnershipBlocker("review-blocked", f"{task_id} repair lacks continuity identities")
    previous = normalize_subagent_provenance(previous_value)
    if isinstance(continuity_value, RepairContinuity):
        continuity = continuity_value
    else:
        if not isinstance(continuity_value, Mapping) or set(continuity_value) != {
            "binding_id",
            "baseline_identity",
            "evidence_identity",
            "previous_review_identity",
        }:
            raise OwnershipBlocker("review-blocked", f"{task_id} repair continuity is not closed")
        try:
            continuity = RepairContinuity(**{key: str(value) for key, value in continuity_value.items()})
        except (TypeError, ValueError) as error:
            raise OwnershipBlocker("review-blocked", f"{task_id} repair continuity is invalid") from error

    workspace = task.get("workspace") if isinstance(task.get("workspace"), Mapping) else {}
    control_root = Path(str(workspace.get("root") or "")).expanduser().resolve()
    if not control_root.is_dir():
        raise OwnershipBlocker("review-blocked", f"{task_id} repair control root is unavailable")
    binding = load_task_execution_binding(control_root, str(task.get("plan_id") or ""), task_id)
    baseline = binding.get("baseline")
    if not isinstance(baseline, Mapping) or not baseline.get("head"):
        raise OwnershipBlocker("review-blocked", f"{task_id} repair baseline identity is unavailable")
    review = handoff.get("acceptance_review") if isinstance(handoff.get("acceptance_review"), Mapping) else {}
    frontier = review.get("repair_frontier") if isinstance(review.get("repair_frontier"), Mapping) else {}
    ownership = binding.get("ownership") if isinstance(binding.get("ownership"), Mapping) else {}
    try:
        expected = RepairContinuity(
            binding_id=str(ownership.get("binding_id") or ""),
            baseline_identity=semantic_digest(dict(baseline)),
            evidence_identity=str(frontier.get("frozen_evidence_reference") or ""),
            previous_review_identity=str(frontier.get("prior_review_id") or ""),
        )
    except ValueError as error:
        raise OwnershipBlocker(
            "review-blocked", f"{task_id} repair frontier continuity is unavailable"
        ) from error
    if continuity != expected:
        raise OwnershipBlocker("review-blocked", f"{task_id} repair continuity identities do not match")
    if isinstance(authorized_replacements, (str, bytes, Mapping)):
        raise OwnershipBlocker("review-blocked", "authorized_replacements must be task IDs")
    replacements = {str(value) for value in (authorized_replacements or [])}
    replaced = current_ownership.get("agent_id") != previous.get("agent_id")
    if replaced and task_id not in replacements:
        raise OwnershipBlocker(
            "review-blocked", f"{task_id} repair owner replacement is not authorized"
        )


def _acceptable_validation_results(item: dict[str, Any]) -> set[str]:
    raw = item.get("acceptable_results")
    if isinstance(raw, list) and raw:
        allowed = {str(value).strip() for value in raw if str(value).strip()}
        if not allowed.issubset({"passed", "skipped", "failed"}):
            raise SystemExit("Task validation acceptable_results must be passed, skipped, or failed")
        return allowed
    expected = str(item.get("expected") or "").strip().lower()
    if expected in {"skipped", "skip"}:
        return {"passed", "skipped"}
    return {"passed"}


def _assert_task_fit_check(handoff: dict[str, Any], task_id: str, state: str) -> None:
    fit = handoff.get("task_fit_check")
    if not isinstance(fit, dict) or not fit:
        raise SystemExit("Executor result completed or partial state requires task_fit_check")
    fit_task = fit.get("task") or fit.get("related_task")
    if fit_task != task_id:
        raise SystemExit(
            f"Executor result task_fit_check task mismatch: expected {task_id}, got {fit_task or 'missing'}"
        )
    allowed = {"clean", "repaired"} if state == "completed" else TASK_FIT_RESULTS
    if fit.get("result") not in allowed:
        allowed_text = " or ".join(sorted(allowed))
        raise SystemExit(f"Executor result task_fit_check result must be {allowed_text}")


def _assert_changed_paths_in_write_scope(handoff: dict[str, Any], task_files: dict[str, Any]) -> None:
    write_scope = {str(path).strip().removeprefix("./") for path in _as_list(task_files.get("write"))}
    changes = handoff.get("changes") if isinstance(handoff.get("changes"), dict) else {}
    for item in _as_list(changes.get("files")):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip().removeprefix("./")
        if path and path not in write_scope:
            raise SystemExit(f"Executor result changed path is outside task write scope: {path}")


def _assert_handoff_review_matches_task(
    handoff: dict[str, Any], task: dict[str, Any], state: str
) -> str | None:
    compiled_required = task.get("review_required") is True
    review = handoff.get("acceptance_review") if isinstance(handoff.get("acceptance_review"), dict) else {}
    handoff_required = review.get("required") is True
    if compiled_required != handoff_required:
        raise SystemExit("Executor result acceptance_review.required must match compiled review_required")
    if compiled_required and state == "completed" and review.get("verdict") != "accept":
        raise SystemExit("Review-required task cannot complete without acceptance_review.verdict: accept")
    if not compiled_required or state != "completed":
        return None
    fit = handoff.get("task_fit_check") if isinstance(handoff.get("task_fit_check"), dict) else {}
    repaired = fit.get("result") == "repaired"
    mode = review.get("review_mode")
    reset_initial = mode == "initial" and review.get("review_reset") is not None
    if repaired and mode != "repair" and not reset_initial:
        raise SystemExit("Repaired task completion requires a sequenced repair acceptance_review")
    if mode is not None:
        try:
            from review_runtime import ReviewContractError, validate_task_acceptance_review
            validated = validate_task_acceptance_review(review)
        except (ReviewContractError, TypeError, ValueError) as error:
            raise SystemExit(f"Task acceptance review is invalid: {error}") from error
        if validated.verdict != "accepted":
            raise SystemExit("Review-required task cannot complete without an accepted task review")
        if validated.target_identity["artifact_id"] != str(task.get("task_id")):
            raise SystemExit("Task acceptance review target identity does not match the completed task")
        if validated.review_mode == "repair":
            repositories = [
                item for item in _as_list(handoff.get("repository"))
                if isinstance(item, dict) and item.get("target_kind") == "git-backed"
            ]
            if len(repositories) != 1:
                raise SystemExit("Task repair review requires one observed Git repository identity")
            root = Path(str(repositories[0].get("root") or "")).expanduser().resolve()
            head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
            tree = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], capture_output=True, text=True)
            if head.returncode or tree.returncode:
                raise SystemExit("Task repair review Git identity is unavailable")
            if (review.get("reviewed_head") != head.stdout.strip()
                    or validated.target_identity["source_tree"] != tree.stdout.strip()):
                raise SystemExit("Task repair review does not match the observed Git head/tree identity")
        if validated.review_mode == "initial" and validated.review_reset is not None:
            return "initial-reset"
        return validated.review_mode
    return None


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


def _section(body: str, name: str) -> list[str]:
    lines = body.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if re.match(rf"^##\s+(?:\d+(?:\.\d+)?\s+)?{re.escape(name)}\s*$", line.strip(), re.IGNORECASE):
            start = index + 1
            break
    if start is None:
        return []
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return lines[start:end]


def _section_table(body: str, name: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in _section(body, name):
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows[1:] if rows else []


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


def _compile_task_validation(
    task: dict[str, Any], task_body: str, source_ids: list[str], records: dict[str, str]
) -> list[Any]:
    validation_items = _as_list(task.get("validation"))
    if validation_items:
        return [_compile_structured_validation_item(item) for item in validation_items]
    if _section_table(task_body, "Validation"):
        raise SystemExit(
            "Untyped Validation table row is legacy-untyped; migrate to front-matter validation with explicit kind"
        )
    raise SystemExit(
        "Task validation must declare front-matter items with explicit kind; TEST-ID fallback is not executable terminal validation"
    )


def _task_context(args: argparse.Namespace) -> tuple[Path, Path, dict[str, Any], str, dict[str, str], list[Path]]:
    root = resolve_workspace_root(args)
    task_root = root / ".work-bundle/orchestration/plan"
    task_path = _input_path(args.task, root, task_root, "task")
    task_data, task_body = _read_structured(task_path)
    task_id = _artifact_id(task_data, "id", task_path)
    plan_id = _artifact_id(task_data, "plan_id", task_path)
    _, plan_data = _find_plan(root, plan_id)
    source_paths = _resolve_spec_paths(root, task_data, plan_data)
    records: dict[str, str] = {}
    for source_path in source_paths:
        _, body = _read_structured(source_path)
        for identifier, value in _source_records(source_path, body).items():
            if identifier in records and records[identifier] != value:
                raise SystemExit(f"Ambiguous source ID {identifier} across linked specifications")
            records[identifier] = value
    return root, task_path, task_data, task_body, records, source_paths


def _contains_resolved_source_record(value: Any, record: str) -> bool:
    if isinstance(value, str):
        return record in value
    if isinstance(value, dict):
        return any(_contains_resolved_source_record(item, record) for item in value.values())
    if isinstance(value, list):
        return any(_contains_resolved_source_record(item, record) for item in value)
    return False


def _compile_task_brief(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    root, task_path, task, task_body, records, source_paths = _task_context(args)
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
    forbidden_files = _as_list(files.get("forbidden")) or _as_list(task.get("forbidden_files"))

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

    interfaces = task.get("interfaces") if isinstance(task.get("interfaces"), dict) else {}
    if not interfaces:
        inferred_interfaces: dict[str, list[str]] = {"consumes": [], "produces": []}
        for cells in _section_table(task_body, "Files and interfaces"):
            identifier = next((cell.strip("` ") for cell in cells if SOURCE_ID_RE.fullmatch(cell.strip("` "))), None)
            direction = next((cell.lower() for cell in cells if cell.lower() in {"consume", "consumes", "produce", "produces"}), None)
            if identifier and direction:
                inferred_interfaces["produces" if direction.startswith("produce") else "consumes"].append(identifier)
        interfaces = inferred_interfaces
    api_ids = [sid for sid in source_ids if sid.startswith(("API-", "IFACE-"))]
    if api_ids and not _as_list(interfaces.get("consumes")) and not _as_list(interfaces.get("produces")):
        interfaces = {"consumes": api_ids, "produces": []}

    validation_value = _compile_task_validation(task, task_body, source_ids, records)
    executor_profile = _compile_executor_profile(task, task_path)
    evidence_applicability = task_evidence_applicability(task)

    goal_lines = [line.strip() for line in _section(task_body, "Goal") if line.strip()]
    resolved_goal = task.get("goal") or (goal_lines[0] if goal_lines else None) or task.get("name") or task_id
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
    target.write_text("\n".join(_dump_yaml(brief)) + "\n", encoding="utf-8")
    return target


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Git command failed for review package: {' '.join(arguments[:2])}")
    return result.stdout


def _resolve_commit(root: Path, reference: str) -> str:
    return _git(root, "rev-parse", "--verify", f"{reference}^{{commit}}").strip()


def _untracked_diff(root: Path, path: str) -> str:
    if _protected_project_path(path, root):
        return f"diff --git a/{path} b/{path}\nnew file mode (content withheld: protected path)\n"
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--no-ext-diff", "--binary", "--no-index", "--", "/dev/null", path],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise SystemExit(f"Git command failed for untracked review path: {path}")
    return result.stdout


def _paths_from_name_status(line: str) -> list[str]:
    cells = line.split("\t")
    return cells[1:] if len(cells) > 1 else []


def _write_scope_match(path: str, write_paths: list[str]) -> bool:
    normalized = path.removeprefix("./")
    for write in write_paths:
        write_n = str(write).removeprefix("./").rstrip("/")
        if normalized == write_n or normalized.startswith(f"{write_n}/"):
            return True
    return False


def _partition_name_status(
    names: list[str], write_paths: list[str]
) -> tuple[list[str], list[str]]:
    in_scope: list[str] = []
    out_scope: list[str] = []
    for line in names:
        paths = _paths_from_name_status(line)
        scoped = [path for path in paths if _write_scope_match(path, write_paths)]
        other = [path for path in paths if path not in scoped]
        status = line.split("\t", 1)[0]
        if scoped:
            in_scope.append(line if not other else "\t".join([status, *scoped]))
        if other:
            out_scope.append(line if not scoped else "\t".join([status, *other]))
    return in_scope, out_scope


def _bounded_changed_diff(
    root: Path, base: str, head: str | None, names: list[str]
) -> str:
    path_groups = [_paths_from_name_status(line) for line in names]
    safe_paths = sorted(
        {path for paths in path_groups if not any(_protected_project_path(p, root) for p in paths) for path in paths}
    )
    arguments = ["diff", "--no-ext-diff", "--binary", "--unified=3", base]
    if head is not None:
        arguments.append(head)
    diff = _git(root, *arguments, "--", *safe_paths) if safe_paths else ""
    protected = sorted(
        {path for paths in path_groups if any(_protected_project_path(p, root) for p in paths) for path in paths}
    )
    for path in protected:
        diff += f"diff --git a/{path} b/{path}\n(content withheld: protected path)\n"
    return diff


def _review_diff(
    root: Path, base: str, head_reference: str, write_paths: list[str]
) -> tuple[str, str, list[str], list[str]]:
    if head_reference.lower() not in WORKTREE_REFS:
        head = _resolve_commit(root, head_reference)
        names = [line for line in _git(root, "diff", "--name-status", base, head, "--").splitlines() if line]
        in_scope, out_scope = _partition_name_status(names, write_paths)
        diff = _bounded_changed_diff(root, base, head, in_scope)
        return head, diff, in_scope, out_scope

    names = [line for line in _git(root, "diff", "--name-status", base, "--").splitlines() if line]
    untracked = [line for line in _git(root, "ls-files", "--others", "--exclude-standard", "--").splitlines() if line]
    for path in untracked:
        names.append(f"A\t{path}")
    in_scope, out_scope = _partition_name_status(names, write_paths)
    diff = _bounded_changed_diff(root, base, None, in_scope)
    untracked_set = set(untracked)
    for line in in_scope:
        for path in _paths_from_name_status(line):
            if path in untracked_set:
                diff += _untracked_diff(root, path)
    digest = hashlib.sha256(("\n".join(in_scope) + "\n" + diff).encode("utf-8")).hexdigest()
    return f"worktree:{digest}", diff, in_scope, out_scope


def _redact_diff(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if "BEGIN PRIVATE KEY" in line or "END PRIVATE KEY" in line:
            lines.append("<redacted credential material>")
            continue
        lines.append(SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}: <redacted>", line))
    return "\n".join(lines)


def _markdown_items(values: list[Any], empty: str = "None.") -> list[str]:
    if not values:
        return [f"- {empty}"]
    result = []
    for value in values:
        if isinstance(value, dict):
            summary = ", ".join(f"{key}: {item}" for key, item in value.items())
            result.append(f"- `{summary}`")
        else:
            result.append(f"- {value}")
    return result


def build_review_package(args: argparse.Namespace) -> Path:
    if not args.handoff or not args.base or not args.head:
        raise SystemExit("build-review-package requires --handoff, --base, and --head")
    target, brief_document = _compile_task_brief(args)
    root = resolve_workspace_root(args)
    task = brief_document["task_brief"]
    task_id = str(task["task_id"])
    plan_id = str(task.get("plan_id") or "")
    if not plan_id:
        raise SystemExit(f"Task brief is missing plan_id for {task_id}")
    handoff_root = root / ".work-bundle/orchestration/handoff"
    handoff_path = _input_path(args.handoff, root, handoff_root, "handoff")
    handoff, _ = _read_structured(handoff_path)
    validated = validate_executor_result_for_task(handoff, task, observe=True, **_observation_kwargs(args))
    knowledge_disposition = validated["knowledge_disposition"]
    review_request = handoff.get("acceptance_review") if isinstance(handoff.get("acceptance_review"), dict) else {}
    review_mode = str(review_request.get("review_mode") or "initial")
    if review_mode not in {"initial", "repair"}:
        raise SystemExit("review-blocked: review_mode must be initial or repair")
    repair_frontier: dict[str, Any] | None = None
    if review_mode == "repair":
        try:
            from review_runtime import ReviewContractError, _repair_frontier
            repair_frontier = dict(_repair_frontier(review_request.get("repair_frontier")))
        except (ReviewContractError, TypeError, ValueError) as error:
            raise SystemExit(f"review-blocked: invalid repair frontier: {error}") from error
    elif review_request.get("repair_frontier") not in (None, {}):
        raise SystemExit("review-blocked: initial review cannot carry repair_frontier")
    binding = load_task_execution_binding(root, plan_id, task_id)
    execution_root = Path(str(binding["execution_path"])).resolve()

    base = _resolve_commit(execution_root, str(args.base))
    write_paths = [str(path) for path in _as_list((task.get("files") or {}).get("write"))]
    head, diff, name_status, out_of_scope = _review_diff(
        execution_root, base, str(args.head), write_paths
    )
    if repair_frontier is not None:
        base_tree = _git(execution_root, "rev-parse", f"{base}^{{tree}}").strip()
        if head.startswith("worktree:"):
            raise SystemExit("review-blocked: repair review requires a committed repaired identity")
        head_tree = _git(execution_root, "rev-parse", f"{head}^{{tree}}").strip()
        if repair_frontier["previous_reviewed_identity"]["source_tree"] != base_tree:
            raise SystemExit("review-blocked: repair base does not match previous reviewed identity")
        if repair_frontier["repaired_identity"]["source_tree"] != head_tree:
            raise SystemExit("review-blocked: repair head does not match repaired identity")
    omitted_diff_bytes = 0
    if len(diff.encode("utf-8")) > MAX_DIFF_BYTES or diff.count("\n") > MAX_DIFF_LINES:
        oversized = ", ".join(
            sorted({path for line in name_status for path in _paths_from_name_status(line)})
        ) or "unknown"
        if head.startswith("worktree:"):
            raise SystemExit(
                "review-blocked: oversized uncommitted task-local diff has no immutable "
                f"source identity (oversized paths: {oversized})"
            )
        omitted_diff_bytes = len(diff.encode("utf-8"))
        base_tree = _git(execution_root, "rev-parse", f"{base}^{{tree}}").strip()
        head_tree = _git(execution_root, "rev-parse", f"{head}^{{tree}}").strip()
        diff_digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        changed_paths = sorted(
            {path for line in name_status for path in _paths_from_name_status(line)}
        )
        diff = "\n".join(
            [
                "Exact source diff reference (content omitted from this bounded packet).",
                f"Base commit: {base}",
                f"Base tree: {base_tree}",
                f"Head commit: {head}",
                f"Head tree: {head_tree}",
                f"Task-local diff SHA-256: {diff_digest}",
                "Changed paths:",
                *[f"- {path}" for path in changed_paths],
                "Review the exact Git diff between these commits, restricted to the changed paths above.",
            ]
        )
    else:
        diff = _redact_diff(diff)

    changes = handoff.get("changes") if isinstance(handoff.get("changes"), dict) else {}
    handoff_files = [item for item in _as_list(changes.get("files")) if isinstance(item, dict)]
    symbols = sorted(
        {str(symbol) for item in handoff_files for symbol in _as_list(item.get("symbols")) if symbol}
    )
    validation = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else {}
    validation_commands = [item for item in _as_list(validation.get("commands")) if isinstance(item, dict)]
    compiled_validation = {
        str(item.get("command") or ""): item
        for item in _as_list(task.get("validation"))
        if isinstance(item, dict)
    }
    normalized_validation = []
    for position, item in enumerate(validation_commands, start=1):
        compiled = compiled_validation.get(str(item.get("command") or ""), {})
        normalized_validation.append({**item, "id": item.get("id") or compiled.get("id") or f"validation-{position:03d}"})
    evidence_projection = project_validation_evidence(
        normalized_validation,
        evidence_capability=task.get("evidence_capability") if isinstance(task.get("evidence_capability"), dict) else {},
        observed=validated.get("observed_validation"),
        expansion_reason=("failed_validation" if any(item.get("result") == "failed" for item in normalized_validation) else None),
    )
    unresolved = _as_list(handoff.get("unresolved"))
    evidence = {
        "changed_files": name_status,
        "changed_symbols": symbols,
        "validation": evidence_projection,
        "unresolved": unresolved,
        "knowledge_disposition": knowledge_disposition,
    }
    _assert_no_credential_values(evidence, "review evidence")

    required = [f"Goal: {task.get('goal')}", *task.get("requirements", []), *task.get("constraints", [])]
    interfaces = task.get("interfaces", {})
    if isinstance(interfaces, dict):
        required.extend(_as_list(interfaces.get("consumes")))
        required.extend(_as_list(interfaces.get("produces")))
    assertions = [
        *[f"rule {item['id']}: {item['requirement']}" for item in task.get("allocated_rules", [])],
        f"methodology {task['methodology'].get('primary')}: skills {', '.join(map(str, task['methodology'].get('skills', []))) or 'none'}",
    ]
    allowed_scope = list(dict.fromkeys([*task.get("files", {}).get("write", []), *task.get("files", {}).get("read", [])]))
    lines = [
        "# Task Review Package",
        "",
        f"Task: {task_id}",
        f"Base: {base}",
        f"Head: {head}",
        f"Review mode: {review_mode}",
        "",
        "## Required behavior",
        *_markdown_items(required),
        "",
        "## Accepted Truth Basis",
        *_markdown_items([task.get("truth_basis", {})]),
        "",
        "## Semantic authority",
        *_markdown_items([task.get("semantic_authority", {})]),
        "",
        "## Evidence capability",
        *_markdown_items([task.get("evidence_capability", {})]),
        "",
        "## Allowed scope",
        *_markdown_items(allowed_scope),
        "",
        "## Changed files",
        *_markdown_items(name_status),
        "",
        "## Changed symbols",
        *_markdown_items(symbols),
        "",
        "## Validation reported",
        *_markdown_items(evidence_projection),
        "",
        "## Knowledge disposition",
        *_markdown_items([knowledge_disposition]),
        "",
        "## Allocated rule and methodology assertions",
        *_markdown_items(assertions),
        "",
        "## Unresolved concerns",
        *_markdown_items(unresolved),
        "",
        "## Diff",
        "```diff",
        diff.rstrip(),
        "```",
    ]
    if repair_frontier is not None:
        lines.extend(
            [
                "",
                "## Repair frontier",
                *_markdown_items(
                    [{
                        "prior_review_id": repair_frontier["prior_review_id"],
                        "blocking_finding_ids": repair_frontier["blocking_finding_ids"],
                        "previous_reviewed_identity": repair_frontier["previous_reviewed_identity"],
                        "repaired_identity": repair_frontier["repaired_identity"],
                        "affected_boundaries": repair_frontier["affected_boundaries"],
                        "frozen_evidence_reference": repair_frontier["frozen_evidence_reference"],
                    }]
                ),
            ]
        )
    if out_of_scope:
        lines.extend(
            [
                "",
                "## Out-of-scope changes",
                *_markdown_items(out_of_scope),
            ]
        )
    lines.extend(
        [
            "",
            "## Review rubric",
            "1. Required behavior is satisfied.",
            "2. Listed out-of-scope diagnostics are expected sibling or prior changes, not a defect in this task.",
            "3. Methodology and allocated-rule obligations are satisfied.",
            "4. Accepted purpose, source evidence, decision authority, expected delta, and test oracle agree.",
            "5. Knowledge disposition is task-local, evidence-backed, and grants no persistence authority.",
            "6. Validation evidence is sufficient and task-scoped.",
            "7. Code quality has no blocking defect.",
        ]
    )
    package = "\n".join(lines).rstrip() + "\n"
    if out_of_scope and "## Out-of-scope changes" not in package:
        raise SystemExit("Review package omitted required out-of-scope changes section")
    _assert_no_credential_values(package, "review package")
    review_target = target.with_name("review-package.md")
    review_target.parent.mkdir(parents=True, exist_ok=True)
    review_target.write_text(package, encoding="utf-8")
    metrics = compiled_context_metrics(
        task,
        review_package=package,
        evidence_projection=evidence_projection,
        omitted_by_reference_bytes=omitted_diff_bytes,
        expansion_reason=next(
            (item.get("expansion_reason") for item in evidence_projection if item.get("expansion_reason")),
            None,
        ),
    )
    review_target.with_name("review-package-metrics.json").write_text(
        json.dumps({"compiled_context_metrics": metrics}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return review_target


def cmd_build_task_brief(args: argparse.Namespace) -> None:
    target = build_task_brief(args)
    print(target.relative_to(resolve_workspace_root(args)).as_posix())


def cmd_build_review_package(args: argparse.Namespace) -> None:
    target = build_review_package(args)
    print(target.relative_to(resolve_workspace_root(args)).as_posix())


def cmd_observe_task_validation(args: argparse.Namespace) -> None:
    _, brief_document = _compile_task_brief(args)
    task = brief_document["task_brief"]
    runtime = _observation_kwargs(args)
    observed = _observe_completed_validation(
        {},
        task,
        task["validation"],
        None,
        **{
            key: runtime[key]
            for key in (
                "workspace_id",
                "execution_id",
                "repository_id",
                "execution_runtime_root",
                "accepted_dependency_deltas",
            )
        },
    )
    print(json.dumps({"validation": observed}, sort_keys=True))


def cmd_validate_executor_result(args: argparse.Namespace) -> None:
    if not args.handoff:
        raise SystemExit("validate-executor-result requires --handoff")
    _, brief_document = _compile_task_brief(args)
    root = resolve_workspace_root(args)
    task = brief_document["task_brief"]
    handoff_root = root / ".work-bundle/orchestration/handoff"
    handoff_path = _input_path(args.handoff, root, handoff_root, "handoff")
    handoff, _ = _read_structured(handoff_path)
    validate_executor_result_for_task(handoff, task, observe=True, **_observation_kwargs(args))
    print(handoff_path.relative_to(root).as_posix())


def cmd_create_accepted_base_absence_receipt(args: argparse.Namespace) -> None:
    root = resolve_workspace_root(args)
    reference = create_accepted_base_absence_receipt(
        root,
        str(args.plan_id),
        str(args.task_id),
        str(args.expected_head),
        str(args.expected_tree),
        str(args.proposed_handoff_id),
        str(args.proposed_review_id),
        str(args.final_head),
        str(args.final_tree),
    )
    print(json.dumps(reference, sort_keys=True))


def cmd_adopt_existing_recovered_result(args: argparse.Namespace) -> None:
    root = resolve_workspace_root(args)
    reference = adopt_existing_recovered_result(
        root,
        str(args.plan_id),
        str(args.task_id),
        str(args.expected_head),
        str(args.expected_tree),
        str(args.handoff_id),
        str(args.handoff_sha256),
        str(args.review_id),
        str(args.final_head),
        str(args.final_tree),
        {
            "receipt_id": str(args.prior_receipt_id),
            "receipt_sha256": str(args.prior_receipt_sha256),
        },
    )
    print(json.dumps(reference, sort_keys=True))


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
