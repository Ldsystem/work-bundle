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
from typing import Any

from core import is_relative_to, read_front_matter, resolve_workspace_root
from repository_preflight import capture_repository_evidence, task_caused_paths


SOURCE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]*-\d+$")
AUTH_ALIAS_RE = re.compile(r"^AUTH-\d{3}$")
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
    "incapable": "task",
    "contradictory": "specification",
    "stale": "task",
    "wrong_boundary": "plan",
    "failed": "task",
    "missing": "plan",
    "unexecuted": "task",
}
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


def _split_top_level(value: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if quote and char == "\\":
            escaped = True
            continue
        if char in {'"', "'"}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if quote:
            continue
        if char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        elif char == delimiter and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def _split_key_value(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise SystemExit(f"Invalid YAML mapping entry: {value}")
    key, raw = value.split(":", 1)
    return key.strip().strip("'\""), raw.strip()


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [_parse_scalar(part) for part in _split_top_level(inner)]
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        result: dict[str, Any] = {}
        for part in _split_top_level(inner):
            key, raw = _split_key_value(part)
            result[key] = _parse_scalar(raw)
        return result
    if value[:1] == value[-1:] and value[:1] in {'"', "'"}:
        if value.startswith('"'):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def parse_yaml_subset(text: str) -> dict[str, Any]:
    """Parse the compact YAML subset used by orchestration contracts."""

    rows: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        rows.append((indent, raw.strip()))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(rows) or rows[index][0] < indent:
            return {}, index
        is_list = rows[index][0] == indent and rows[index][1].startswith("- ")
        container: Any = [] if is_list else {}
        while index < len(rows):
            row_indent, content = rows[index]
            if row_indent < indent:
                break
            if row_indent > indent:
                raise SystemExit(f"Invalid YAML indentation near: {content}")
            if is_list:
                if not content.startswith("- "):
                    break
                item_text = content[2:].strip()
                if not item_text:
                    item, index = parse_block(index + 1, indent + 2)
                elif item_text.startswith("{"):
                    item = _parse_scalar(item_text)
                    index += 1
                elif ":" in item_text and not item_text.startswith(("'", '"', "`")):
                    key, raw_value = _split_key_value(item_text)
                    item = {key: _parse_scalar(raw_value)}
                    index += 1
                    if index < len(rows) and rows[index][0] > indent:
                        continuation, index = parse_block(index, indent + 2)
                        if not isinstance(continuation, dict):
                            raise SystemExit(f"Invalid YAML list mapping near: {item_text}")
                        item.update(continuation)
                else:
                    item = _parse_scalar(item_text)
                    index += 1
                container.append(item)
                continue

            if content.startswith("- "):
                break
            key, raw_value = _split_key_value(content)
            index += 1
            if raw_value:
                container[key] = _parse_scalar(raw_value)
            elif index < len(rows) and rows[index][0] > indent:
                container[key], index = parse_block(index, rows[index][0])
            else:
                container[key] = {}
        return container, index

    if not rows:
        return {}
    parsed, index = parse_block(0, rows[0][0])
    if index != len(rows) or not isinstance(parsed, dict):
        raise SystemExit("Expected a YAML mapping")
    return parsed


def _read_structured(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end < 0:
            raise SystemExit(f"Unterminated front matter: {path}")
        return parse_yaml_subset(raw[4:end]), raw[end + 5 :]
    return parse_yaml_subset(raw), ""


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "" or value == {}:
        return []
    return value if isinstance(value, list) else [value]


def _input_path(raw: str | Path, root: Path, allowed: Path, label: str) -> Path:
    path = Path(raw).expanduser()
    path = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not is_relative_to(path, allowed.resolve()):
        raise SystemExit(f"{label} path escapes its allowed root: {path}")
    relative = path.relative_to(root.resolve()).as_posix()
    if relative.startswith(".work-bundle/knowledge/") or relative.startswith("credentials/"):
        raise SystemExit(f"{label} path uses a forbidden protected source: {relative}")
    if not path.is_file():
        raise SystemExit(f"{label} file not found: {path}")
    return path


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


def _resolve_spec_paths(root: Path, task_data: dict[str, Any], plan_data: dict[str, Any]) -> list[Path]:
    references = _as_list(task_data.get("source_spec")) or _as_list(plan_data.get("source_spec"))
    if not references:
        raise SystemExit("Task/root plan does not declare source_spec")
    spec_root = root / ".work-bundle/orchestration/spec"
    result: list[Path] = []
    for reference in references:
        raw = str(reference)
        if "/" in raw or raw.endswith(".md"):
            result.append(_input_path(raw, root, spec_root, "source specification"))
            continue
        matches: list[Path] = []
        for candidate in sorted(spec_root.glob("*/*.md")):
            data, _ = _read_structured(candidate)
            if str(data.get("id", "")) == raw:
                matches.append(candidate)
        if len(matches) != 1:
            raise SystemExit(f"Expected one source specification for {raw}; found {len(matches)}")
        result.append(matches[0])
    return result


def _strip_markup(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).strip()


def _source_records(path: Path, body: str) -> dict[str, str]:
    records: dict[str, str] = {}

    def add(identifier: str, value: str) -> None:
        if AUTH_ALIAS_RE.fullmatch(identifier):
            return
        value = _strip_markup(value)
        if not value:
            return
        previous = records.get(identifier)
        if previous is not None and previous != value:
            raise SystemExit(f"Ambiguous source ID {identifier} in {path}")
        records[identifier] = value

    for line in body.splitlines():
        bullet = re.match(r"^\s*[-*]\s+\*\*([A-Z][A-Z0-9_-]*-\d+)\*\*\s*:\s*(.+)$", line)
        if bullet:
            add(bullet.group(1), bullet.group(2))
            continue
        heading = re.match(r"^#{2,6}\s+([A-Z][A-Z0-9_-]*-\d+)\s*(?:[:—-]\s*)?(.*)$", line)
        if heading and heading.group(2).strip():
            add(heading.group(1), heading.group(2))
            continue
        plain = re.match(r"^\s*([A-Z][A-Z0-9_-]*-\d+)\s*:\s*(.+)$", line)
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


def _resolve_reference(value: Any, records: dict[str, str], source_paths: list[Path]) -> Any:
    if isinstance(value, str) and SOURCE_ID_RE.fullmatch(value):
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
        "expected_delta": _resolve_reference(list_fields["expected_delta"], records, source_paths),
        "conflict_status": conflict_status,
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
        "mutating": True,
        "baseline": None,
    }
    _assert_no_overlapping_mutating_siblings(control_root, binding)
    _persist_binding(binding, control_root)
    return binding


def load_task_execution_binding(control_root: Path, plan_id: str, task_id: str) -> dict[str, Any]:
    binding = _read_binding_file(_binding_path(control_root.expanduser().resolve(), plan_id, task_id))
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
    }
    if not required.issubset(binding):
        raise SystemExit("Task execution binding provenance is invalid")
    if binding.get("plan_id") != plan_id or binding.get("task_id") != task_id:
        raise SystemExit("Task execution binding identity mismatch")
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


def _observe_validation_item(item: dict[str, Any], execution_root: Path, task: dict[str, Any]) -> dict[str, Any]:
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
    completed = subprocess.run(
        command,
        shell=True,
        cwd=str(execution_root),
        capture_output=True,
        text=True,
        check=False,
    )
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
) -> None:
    write_paths = [str(path) for path in _as_list(task_files.get("write"))]
    forbidden = [str(path) for path in _as_list(task_files.get("forbidden"))]
    for relative in caused:
        if _path_is_forbidden(relative, forbidden) or not _write_scope_match(relative, write_paths):
            raise SystemExit(f"Unauthorized task-caused delta outside write scope: {relative}")


def _observe_completed_validation(
    handoff: dict[str, Any],
    task: dict[str, Any],
    required_items: list[dict[str, Any]],
    reported_commands: dict[str, dict[str, Any]],
    *,
    workspace_id: str | None = None,
    execution_id: str | None = None,
    repository_id: str | None = None,
    execution_runtime_root: str | None = None,
) -> list[dict[str, Any]]:
    if "harness_receipt" in handoff or (
        isinstance(handoff.get("validation"), dict) and "harness_receipt" in handoff["validation"]
    ):
        raise SystemExit("Executor-minted harness_receipt is not independent proof")
    control_root_raw = (task.get("workspace") or {}).get("root") if isinstance(task.get("workspace"), dict) else None
    if not control_root_raw:
        raise SystemExit("Task execution binding is missing harness provenance")
    control_root = Path(str(control_root_raw))
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
    for item in required_items:
        observed = _observe_validation_item(item, execution_root, task)
        command = str(item.get("command")).strip()
        reported_item = reported_commands[command]
        if reported_item.get("result") != observed["result"]:
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
    _assert_task_caused_delta_in_write_scope(caused, task_files)
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
    _assert_task_caused_delta_in_write_scope(caused, task_files)

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
    _assert_handoff_review_matches_task(handoff, task, state)
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
        )
        evidence_closure = _validate_evidence_closure(
            handoff, task, state, reported_commands, observed_validation
        )
    if state == "completed" and capability.get("result") == "mapped":
        if observed_validation is None or not isinstance(evidence_closure, dict) or evidence_closure.get("result") != "passed":
            raise SystemExit(
                "evidence-closure-blocked: completed mapped invariants require produced harness observations and passed evidence closure"
            )
    return {
        "knowledge_disposition": knowledge_disposition,
        "unresolved": unresolved,
        "result_state": state,
        "evidence_applicability": evidence_applicability,
        "evidence_closure": evidence_closure,
        **({"observed_validation": observed_validation} if observed_validation is not None else {}),
    }


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


def _assert_handoff_review_matches_task(handoff: dict[str, Any], task: dict[str, Any], state: str) -> None:
    compiled_required = task.get("review_required") is True
    review = handoff.get("acceptance_review") if isinstance(handoff.get("acceptance_review"), dict) else {}
    handoff_required = review.get("required") is True
    if compiled_required != handoff_required:
        raise SystemExit("Executor result acceptance_review.required must match compiled review_required")
    if compiled_required and state == "completed" and review.get("verdict") != "accept":
        raise SystemExit("Review-required task cannot complete without acceptance_review.verdict: accept")


def _yaml_scalar(value: Any) -> str:
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
            key: value if key in {"id", "invariant_ids"} else _resolve_reference(value, records, source_paths)
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
    brief = {
        "task_brief": {
            "task_id": task_id,
            "plan_id": plan_id,
            "source_ids": source_ids,
            "goal": resolved_goal,
            "truth_basis": truth_basis,
            "requirements": source_by_kind["requirements"],
            "constraints": source_by_kind["constraints"],
            "interfaces": {
                "consumes": _resolve_reference(_as_list(interfaces.get("consumes")), records, source_paths),
                "produces": _resolve_reference(_as_list(interfaces.get("produces")), records, source_paths),
            },
            "files": {"read": read_files, "write": write_files, "forbidden": forbidden_files},
            "methodology": {"primary": methodology.get("primary", "direct"), "skills": skill_names},
            "allocated_rules": rules,
            "executor_profile": executor_profile,
            "evidence_applicability": evidence_applicability,
            "workspace": {"root": str(root)},
            "validation": validation,
            "evidence_capability": evidence_capability,
            "handoff_contract": "executor-result-v1",
            "review_required": review_required,
        }
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
    binding = load_task_execution_binding(root, plan_id, task_id)
    execution_root = Path(str(binding["execution_path"])).resolve()

    base = _resolve_commit(execution_root, str(args.base))
    write_paths = [str(path) for path in _as_list((task.get("files") or {}).get("write"))]
    head, diff, name_status, out_of_scope = _review_diff(
        execution_root, base, str(args.head), write_paths
    )
    if len(diff.encode("utf-8")) > MAX_DIFF_BYTES or diff.count("\n") > MAX_DIFF_LINES:
        oversized = ", ".join(
            sorted({path for line in name_status for path in _paths_from_name_status(line)})
        ) or "unknown"
        raise SystemExit(
            "review-blocked: task-local review diff exceeds the bounded package limit "
            f"(oversized paths: {oversized}). This is a compiler-or-plan defect, "
            "not a reason to add implementation tasks."
        )
    diff = _redact_diff(diff)

    changes = handoff.get("changes") if isinstance(handoff.get("changes"), dict) else {}
    handoff_files = [item for item in _as_list(changes.get("files")) if isinstance(item, dict)]
    symbols = sorted(
        {str(symbol) for item in handoff_files for symbol in _as_list(item.get("symbols")) if symbol}
    )
    validation = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else {}
    validation_commands = [item for item in _as_list(validation.get("commands")) if isinstance(item, dict)]
    unresolved = _as_list(handoff.get("unresolved"))
    evidence = {
        "changed_files": name_status,
        "changed_symbols": symbols,
        "validation": validation_commands,
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
        "",
        "## Required behavior",
        *_markdown_items(required),
        "",
        "## Accepted Truth Basis",
        *_markdown_items([task.get("truth_basis", {})]),
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
        *_markdown_items(validation_commands),
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
    return review_target


def cmd_build_task_brief(args: argparse.Namespace) -> None:
    target = build_task_brief(args)
    print(target.relative_to(resolve_workspace_root(args)).as_posix())


def cmd_build_review_package(args: argparse.Namespace) -> None:
    target = build_review_package(args)
    print(target.relative_to(resolve_workspace_root(args)).as_posix())


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


def _observation_kwargs(args: argparse.Namespace) -> dict[str, str | None]:
    return {
        "workspace_id": getattr(args, "workspace_id", None) or None,
        "execution_id": getattr(args, "execution_id", None) or None,
        "repository_id": getattr(args, "repository_id", None) or None,
        "execution_runtime_root": getattr(args, "execution_runtime_root", None) or None,
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
