#!/usr/bin/env python3
"""Compile disposable, task-bounded executor and reviewer context packets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from core import is_relative_to, read_front_matter, resolve_workspace_root


SOURCE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]*-\d+$")
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
KNOWLEDGE_PERSISTENCE_INSTRUCTION_RE = re.compile(
    r"(?:\.work-bundle/knowledge(?:/|\b)|\bks-[a-z0-9-]+\b)",
    re.IGNORECASE,
)


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
        result.append(text)
    return result


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


def _verified_specification_authority(source_paths: list[Path]) -> set[str]:
    accepted: set[str] = set()
    authority_index = 0
    for source_path in source_paths:
        metadata, _ = _read_structured(source_path)
        if metadata.get("status") != "verified":
            raise SystemExit(f"Task decision_authority requires a verified specification: {source_path}")
        for entry in _as_list(metadata.get("source_knowledge")):
            if isinstance(entry, str) and entry.strip():
                authority_index += 1
                accepted.add(f"AUTH-{authority_index:03d}")
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
        if "none-relevant" in decision_authority or any(
            value not in accepted_authority for value in decision_authority
        ):
            raise SystemExit(
                "Task Truth Basis decision_authority must use none-relevant or verified specification authority"
            )
        compiled_authority = decision_authority
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


def evaluate_knowledge_closure_state(
    *,
    upstream_disposition: str,
    accepted_task_handoffs: list[dict[str, Any]],
    closure_return: str = "missing",
) -> dict[str, Any]:
    if upstream_disposition not in {"required", "not-needed", "completed", "blocked"}:
        raise SystemExit("Invalid upstream Knowledge Base Update disposition")
    if closure_return not in {"missing", "completed", "not-needed", "blocked"}:
        raise SystemExit("Invalid knowledge closure return state")

    triggers: list[dict[str, str]] = []
    for handoff in accepted_task_handoffs:
        review = handoff.get("acceptance_review")
        if not isinstance(review, dict) or review.get("verdict") != "accept":
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
            related = handoff.get("related") if isinstance(handoff.get("related"), dict) else {}
            triggers.append({"task": str(related.get("task") or "unknown"), "action": str(action)})

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
    handoff: dict[str, Any], accepted_source_ids: list[str], accepted_authority_paths: list[str]
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
        if SOURCE_ID_RE.fullmatch(authority):
            if authority not in accepted_source_ids:
                raise SystemExit("Executor result knowledge disposition cites unallocated source authority")
            continue
        if authority not in accepted_authority_paths:
            raise SystemExit("Executor result knowledge disposition path must be in compiled task scope")
    return {"action": action, "reason": reason.strip(), "affected_authority": affected}


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

    validation_value = _as_list(task.get("validation"))
    if not validation_value:
        for cells in _section_table(task_body, "Validation"):
            if len(cells) < 3:
                continue
            validation_value.append(
                {
                    "command": cells[0].strip("`"),
                    "proves": cells[1].strip("`"),
                    "expected": cells[2],
                }
            )
    if not validation_value:
        for identifier in source_ids:
            if identifier.startswith("TEST-"):
                validation_value.append(
                    {"command": records[identifier], "proves": identifier, "expected": records[identifier]}
                )

    goal_lines = [line.strip() for line in _section(task_body, "Goal") if line.strip()]
    resolved_goal = task.get("goal") or (goal_lines[0] if goal_lines else None) or task.get("name") or task_id
    source_by_kind = {
        "requirements": [f"{sid}: {records[sid]}" for sid in source_ids if not sid.startswith(("CON-", "API-", "IFACE-", "TEST-"))],
        "constraints": [f"{sid}: {records[sid]}" for sid in source_ids if sid.startswith("CON-")],
    }
    truth_basis = _compile_truth_basis(task, records, source_paths)
    validation = _resolve_reference(validation_value, records, source_paths)
    acceptance_review = task.get("acceptance_review")
    if acceptance_review in (None, {}):
        review_required = True
    elif not isinstance(acceptance_review, dict):
        raise SystemExit(f"Task acceptance_review must be a mapping: {task_path}")
    else:
        review_required = acceptance_review.get("required", True)
        if not isinstance(review_required, bool):
            raise SystemExit(f"Task acceptance_review.required must be boolean: {task_path}")
    brief = {
        "task_brief": {
            "task_id": task_id,
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
            "executor_profile": task.get("executor_profile")
            if isinstance(task.get("executor_profile"), dict)
            else {"capability": "standard", "context_mode": "compiled-brief"},
            "workspace": {"root": str(root)},
            "validation": validation,
            "handoff_contract": "executor-result-v1",
            "review_required": review_required,
        }
    }
    serialized_brief = json.dumps(brief, ensure_ascii=False)
    for identifier in source_ids:
        if records[identifier] not in serialized_brief:
            raise SystemExit(
                f"Source ID {identifier} from {', '.join(path.as_posix() for path in source_paths)} "
                "is not allocated to a resolved task-brief field"
            )
    _assert_no_credential_values(brief, "task brief")
    target = root / ".work-bundle/runtime/execution" / plan_id / task_id / "task-brief.yaml"
    return target, brief


def build_task_brief(args: argparse.Namespace) -> Path:
    target, brief = _compile_task_brief(args)
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


def _review_diff(root: Path, base: str, head_reference: str) -> tuple[str, str, list[str]]:
    if head_reference.lower() not in WORKTREE_REFS:
        head = _resolve_commit(root, head_reference)
        names = [line for line in _git(root, "diff", "--name-status", base, head, "--").splitlines() if line]
        diff = _bounded_changed_diff(root, base, head, names)
        return head, diff, names

    names = [line for line in _git(root, "diff", "--name-status", base, "--").splitlines() if line]
    diff = _bounded_changed_diff(root, base, None, names)
    untracked = [line for line in _git(root, "ls-files", "--others", "--exclude-standard", "--").splitlines() if line]
    for path in untracked:
        names.append(f"A\t{path}")
        diff += _untracked_diff(root, path)
    digest = hashlib.sha256(("\n".join(names) + "\n" + diff).encode("utf-8")).hexdigest()
    return f"worktree:{digest}", diff, names


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
    handoff_root = root / ".work-bundle/orchestration/handoff"
    handoff_path = _input_path(args.handoff, root, handoff_root, "handoff")
    handoff, _ = _read_structured(handoff_path)
    if handoff.get("type") != "executor-result":
        raise SystemExit(f"Handoff is not executor-result: {handoff_path}")
    related = handoff.get("related") if isinstance(handoff.get("related"), dict) else {}
    related_task = related.get("task") or handoff.get("related_task")
    if related_task != task_id:
        raise SystemExit(f"Handoff task mismatch: expected {task_id}, got {related_task or 'missing'}")
    task_files = task.get("files") if isinstance(task.get("files"), dict) else {}
    accepted_authority_paths = [
        str(value)
        for value in [*_as_list(task_files.get("read")), *_as_list(task_files.get("write"))]
    ]
    knowledge_disposition = _validated_knowledge_disposition(
        handoff, list(task.get("source_ids", [])), accepted_authority_paths
    )

    base = _resolve_commit(root, str(args.base))
    head, diff, name_status = _review_diff(root, base, str(args.head))
    if len(diff.encode("utf-8")) > MAX_DIFF_BYTES or diff.count("\n") > MAX_DIFF_LINES:
        raise SystemExit("Review diff exceeds the bounded package limit")
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
        "",
        "## Review rubric",
        "1. Required behavior is satisfied.",
        "2. No out-of-scope change is present.",
        "3. Methodology and allocated-rule obligations are satisfied.",
        "4. Accepted purpose, source evidence, decision authority, expected delta, and test oracle agree.",
        "5. Knowledge disposition is task-local, evidence-backed, and grants no persistence authority.",
        "6. Validation evidence is sufficient and task-scoped.",
        "7. Code quality has no blocking defect.",
    ]
    package = "\n".join(lines).rstrip() + "\n"
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
