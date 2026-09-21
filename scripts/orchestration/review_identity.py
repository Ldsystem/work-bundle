"""Versioned structural identity projections for orchestration plan artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from artifact_store import (
    canonical_artifact_path,
    family_policy,
    load_catalog,
    read_artifact,
    read_yaml_mapping,
)


CANONICAL_YAML_PLAN_PROJECTION_SCHEMA = "canonical-yaml-plan-tree-v1"
CANONICAL_TASK_AUTHORITY_PROJECTION_SCHEMA = "canonical-task-authority-v1"
SOURCE_ID_PATTERN = r"[A-Z][A-Z0-9_-]*-\d+[A-Z]?"
SOURCE_ID_RE = re.compile(rf"^{SOURCE_ID_PATTERN}$")
SOURCE_BULLET_RE = re.compile(
    rf"^(?P<indent>\s*)[-*+]\s+(?:"
    rf"\*\*(?P<id_bold>{SOURCE_ID_PATTERN})(?P<label>[^*]*)\*\*\s*:?[ \t]*"
    rf"|(?P<id_plain>{SOURCE_ID_PATTERN})\s*(?:—|:|-)[ \t]*)"
)
SOURCE_HEADING_RE = re.compile(
    rf"^(?P<marks>#+)\s+(?:\*\*)?(?P<id_heading>{SOURCE_ID_PATTERN})"
    rf"(?:\*\*)?(?:\s*(?:—|:|-)[ \t]*|\s*$)"
)
SOURCE_TABLE_RE = re.compile(
    rf"^\s*\|\s*(?:\*\*)?(?P<id_table>{SOURCE_ID_PATTERN})(?:\*\*)?\s*\|"
)
CURRENT_PLAN_CATALOG = (
    Path(__file__).resolve().parents[2]
    / "references/assets/orchestration/contract/artifact-family-catalog-v6.yaml"
)
CANONICAL_YAML_CONTROL_FIELDS = frozenset(
    {
        "status", "date_created", "last_updated", "updated_at", "review_id",
        "target_identity", "review_mode", "repair_frontier", "review_reset",
    }
)

def canonical_yaml_plan_value(value: Mapping[str, object]) -> dict[str, object]:
    """Remove only declared top-level lifecycle/control fields from one YAML member."""

    return {
        key: child
        for key, child in sorted(value.items())
        if key not in CANONICAL_YAML_CONTROL_FIELDS
        and not key.startswith("accepted_result")
        and not key.startswith("evidence_reference")
    }


def _normalized_semantic(lines: list[str]) -> str:
    return " ".join(" ".join(line.strip().split()) for line in lines if line.strip())


def _specification_source_records(
    body: str, source_knowledge: object,
) -> dict[str, str]:
    """Project stable named semantic units from a verified specification."""

    lines = body.splitlines()
    records: dict[str, str] = {}
    cursor = 0
    while cursor < len(lines):
        line = lines[cursor]
        heading = SOURCE_HEADING_RE.match(line)
        bullet = SOURCE_BULLET_RE.match(line)
        table = SOURCE_TABLE_RE.match(line)
        match = heading or bullet or table
        if match is None:
            cursor += 1
            continue
        groups = match.groupdict()
        source_id = str(
            groups.get("id_bold")
            or groups.get("id_plain")
            or groups.get("id_heading")
            or groups.get("id_table")
        )
        label = str(groups.get("label") or "").strip().strip("—:- ")
        anchor_semantic = " ".join(
            part for part in (label, line[match.end():].replace("**", "").strip())
            if part
        )
        semantic_lines = [f"{source_id}: {anchor_semantic}".rstrip()]
        next_cursor = cursor + 1
        if heading is not None:
            level = len(str(heading.group("marks")))
            while next_cursor < len(lines):
                next_heading = re.match(r"^(#+)\s+", lines[next_cursor])
                if next_heading is not None and len(next_heading.group(1)) <= level:
                    break
                semantic_lines.append(lines[next_cursor])
                next_cursor += 1
        elif bullet is not None:
            indent = len(str(bullet.group("indent")))
            while next_cursor < len(lines):
                candidate = lines[next_cursor]
                if not candidate.strip():
                    break
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate_indent <= indent:
                    break
                semantic_lines.append(candidate)
                next_cursor += 1
        semantic = _normalized_semantic(semantic_lines)
        if source_id in records:
            raise SystemExit(
                f"Specification contains duplicate source definition: {source_id}"
            )
        records[source_id] = semantic
        cursor = max(next_cursor, cursor + 1)

    if isinstance(source_knowledge, list):
        for index, entry in enumerate(source_knowledge, start=1):
            if not isinstance(entry, Mapping):
                continue
            constraint = entry.get("constraint")
            if isinstance(constraint, str) and constraint.strip():
                records[f"AUTH-{index:03d}"] = " ".join(constraint.split())
    return records


def _source_ids_in(value: object) -> set[str]:
    if isinstance(value, str):
        return {value} if SOURCE_ID_RE.fullmatch(value) else set()
    if isinstance(value, Mapping):
        result: set[str] = set()
        for child in value.values():
            result.update(_source_ids_in(child))
        return result
    if isinstance(value, list):
        result = set()
        for child in value:
            result.update(_source_ids_in(child))
        return result
    return set()


def _global_source_ids(value: object) -> set[str]:
    """Read explicit global decision declarations without promoting alias catalogs."""

    if isinstance(value, str):
        return {value} if SOURCE_ID_RE.fullmatch(value) else set()
    if isinstance(value, Mapping):
        result: set[str] = set()
        for key, child in value.items():
            if key in {"aliases", "production_owners"}:
                continue
            if SOURCE_ID_RE.fullmatch(str(key)):
                result.add(str(key))
            result.update(_global_source_ids(child))
        return result
    if isinstance(value, list):
        result = set()
        for child in value:
            result.update(_global_source_ids(child))
        return result
    return set()


def _applicable_root_allocations(
    root: Mapping[str, object], *, task_ids: set[str], phase_ids: set[str],
) -> tuple[set[str], set[str]]:
    sources: set[str] = set()
    validations: set[str] = set()
    coverage = root.get("source_coverage")
    if not isinstance(coverage, list):
        return sources, validations
    for item in coverage:
        if not isinstance(item, Mapping):
            continue
        allocated_tasks = set(map(str, item.get("task_ids", [])))
        allocated_phases = set(map(str, item.get("phase_ids", [])))
        applicable = bool(allocated_tasks.intersection(task_ids)) or (
            not allocated_tasks and bool(allocated_phases.intersection(phase_ids))
        )
        if not applicable:
            continue
        source_id = item.get("source_id")
        if isinstance(source_id, str) and SOURCE_ID_RE.fullmatch(source_id):
            sources.add(source_id)
        raw_validations = item.get("validation_ids")
        if isinstance(raw_validations, list):
            validations.update(map(str, raw_validations))
    return sources, validations


def _validation_ids(value: Mapping[str, object]) -> set[str]:
    raw = value.get("validation")
    if not isinstance(raw, list):
        return set()
    return {
        str(item.get("id"))
        for item in raw
        if isinstance(item, Mapping) and item.get("id")
    }


def _root_policy_projection(
    value: object, *, source_ids: set[str], task_ids: set[str],
) -> object:
    if not isinstance(value, Mapping):
        return value
    projected: dict[str, object] = {}
    for key, child in value.items():
        if key == "aliases" and isinstance(child, Mapping):
            projected[key] = {
                alias: semantic for alias, semantic in child.items()
                if str(alias) in source_ids
            }
            continue
        if key == "production_owners" and isinstance(child, Mapping):
            projected[key] = {
                owner: task for owner, task in child.items()
                if str(task) in task_ids
            }
            continue
        if SOURCE_ID_RE.fullmatch(str(key)):
            if str(key) in source_ids:
                projected[key] = child
            continue
        if isinstance(child, list) and child and all(
            isinstance(item, str) and SOURCE_ID_RE.fullmatch(item) for item in child
        ):
            projected[key] = [item for item in child if item in source_ids]
            continue
        projected[key] = child
    return projected


def _root_authority_projection(
    root: Mapping[str, object], *, source_ids: set[str], task_ids: set[str],
    phase_ids: set[str], validation_ids: set[str],
) -> dict[str, object]:
    """Return global policy plus only the root allocations applicable to a task closure."""

    value = canonical_yaml_plan_value(root)
    projected = {
        key: value[key]
        for key in (
            "artifact_type", "schema_version", "id", "goal", "purpose", "component",
            "version", "source_spec_id", "semantic_loop",
            "execution_workspace", "completion_criteria",
        )
        if key in value
    }
    for key in ("authority", "strategy"):
        if key in value:
            projected[key] = _root_policy_projection(
                value[key], source_ids=source_ids, task_ids=task_ids
            )
    coverage = value.get("source_coverage")
    if isinstance(coverage, list):
        projected["source_coverage"] = [
            item for item in coverage
            if isinstance(item, Mapping) and (
                bool(_source_ids_in(item).intersection(source_ids))
                or bool(set(map(str, item.get("task_ids", []))).intersection(task_ids))
                or bool(set(map(str, item.get("phase_ids", []))).intersection(phase_ids))
            )
        ]
    strategy = value.get("validation_strategy")
    if isinstance(strategy, list):
        projected["validation_strategy"] = [
            item for item in strategy
            if isinstance(item, Mapping)
            and (
                not item.get("id")
                or str(item.get("id")) in validation_ids
                or bool(_source_ids_in(item).intersection(source_ids))
                or bool(set(map(str, item.get("task_ids", []))).intersection(task_ids))
                or bool(set(map(str, item.get("phase_ids", []))).intersection(phase_ids))
            )
        ]
    phase_index = value.get("phase_index")
    if isinstance(phase_index, list):
        projected["phase_index"] = [
            item for item in phase_index
            if isinstance(item, Mapping) and str(item.get("id") or "") in phase_ids
        ]
    graph = value.get("dependency_graph")
    if isinstance(graph, Mapping):
        projected["dependency_graph"] = {
            key: child for key, child in graph.items()
            if str(key) in task_ids
        }
    return projected


def _phase_authority_projection(
    phase: Mapping[str, object], *, source_ids: set[str], task_ids: set[str],
    validation_ids: set[str],
) -> dict[str, object]:
    """Return phase-wide policy and the task-local membership/allocation slice."""

    value = canonical_yaml_plan_value(phase)
    projected = {
        key: value[key]
        for key in (
            "artifact_type", "schema_version", "id", "plan_id", "order", "depends_on",
            "barriers", "completion_criteria", "allocated_rules", "allocated_skills",
        )
        if key in value
    }
    raw_sources = value.get("source_ids")
    if isinstance(raw_sources, list):
        projected["source_ids"] = [
            item for item in raw_sources if str(item) in source_ids
        ]
    task_index = value.get("task_index")
    if isinstance(task_index, list):
        projected["task_index"] = [
            item for item in task_index
            if isinstance(item, Mapping) and str(item.get("id") or "") in task_ids
        ]
    validation = value.get("validation")
    if isinstance(validation, list):
        projected["validation"] = [
            item for item in validation
            if isinstance(item, Mapping)
            and (
                not item.get("id")
                or str(item.get("id")) in validation_ids
                or bool(_source_ids_in(item).intersection(source_ids))
                or bool(set(map(str, item.get("task_ids", []))).intersection(task_ids))
            )
        ]
    return projected


def load_canonical_plan_tree(
    root: Path,
    plan_id: str,
    *,
    state: str | None = None,
) -> dict[str, Any]:
    """Load one schema-valid plan tree through its declared canonical relationships."""

    anchors = {"workspace_root": root.expanduser().resolve()}
    catalog = load_catalog(CURRENT_PLAN_CATALOG)
    root_policy = family_policy(catalog, "root-plan")
    states = [state] if state is not None else ["active", "archived"]
    roots: list[dict[str, Any]] = []
    for candidate_state in states:
        path = canonical_artifact_path(
            root_policy,
            anchors,
            identity=plan_id,
            state=str(candidate_state),
        )
        if not path.is_file():
            continue
        candidate = read_yaml_mapping(path)
        source_spec_id = str(candidate.get("source_spec_id") or "")
        roots.append(
            read_artifact(
                CURRENT_PLAN_CATALOG,
                "root-plan",
                anchors,
                identity=plan_id,
                state=str(candidate_state),
                bindings={"source_spec": source_spec_id},
            )
        )
    if len(roots) != 1:
        raise SystemExit(f"Plan identity requires one canonical root plan: {plan_id}")

    root_record = roots[0]
    root_data = dict(root_record["data"])
    lifecycle_state = str(root_record["state"])
    phase_ids = [
        str(item.get("id") or "")
        for item in root_data.get("phase_index", [])
        if isinstance(item, dict)
    ]
    if not phase_ids or len(phase_ids) != len(set(phase_ids)):
        raise SystemExit(f"Plan identity requires a unique canonical phase index: {plan_id}")

    phases: dict[str, dict[str, Any]] = {}
    tasks: dict[str, dict[str, Any]] = {}
    for phase_id in phase_ids:
        phase_record = read_artifact(
            CURRENT_PLAN_CATALOG,
            "phase",
            anchors,
            identity=phase_id,
            state=lifecycle_state,
            bindings={"plan": plan_id},
        )
        phase_data = dict(phase_record["data"])
        phases[phase_id] = phase_data
        task_ids = [
            str(item.get("id") or "")
            for item in phase_data.get("task_index", [])
            if isinstance(item, dict)
        ]
        if not task_ids or len(task_ids) != len(set(task_ids)):
            raise SystemExit(
                f"Plan identity requires a unique canonical task index: {phase_id}"
            )
        for task_id in task_ids:
            if task_id in tasks:
                raise SystemExit(f"Plan identity contains duplicate task: {task_id}")
            task_record = read_artifact(
                CURRENT_PLAN_CATALOG,
                "task",
                anchors,
                identity=task_id,
                state=lifecycle_state,
                bindings={"plan": plan_id, "phase": phase_id},
            )
            tasks[task_id] = dict(task_record["data"])
    return {
        "state": lifecycle_state,
        "root": root_data,
        "phases": phases,
        "tasks": tasks,
    }


def canonical_plan_tree_identity(
    root: Path,
    plan_id: str,
    *,
    state: str | None = None,
) -> dict[str, str]:
    """Digest schema-valid canonical content, independent of filenames and indexes."""

    tree = load_canonical_plan_tree(root, plan_id, state=state)
    members: list[dict[str, object]] = [
        {
            "family": "root-plan",
            "id": plan_id,
            "value": canonical_yaml_plan_value(tree["root"]),
        }
    ]
    members.extend(
        {
            "family": "phase",
            "id": phase_id,
            "value": canonical_yaml_plan_value(data),
        }
        for phase_id, data in sorted(tree["phases"].items())
    )
    members.extend(
        {
            "family": "task",
            "id": task_id,
            "value": canonical_yaml_plan_value(data),
        }
        for task_id, data in sorted(tree["tasks"].items())
    )
    payload = {
        "projection_schema": CANONICAL_YAML_PLAN_PROJECTION_SCHEMA,
        "members": members,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {"id": plan_id, "sha256": hashlib.sha256(encoded).hexdigest()}


def canonical_task_authority_identity(
    root: Path,
    plan_id: str,
    task_id: str,
    *,
    state: str | None = None,
) -> dict[str, str]:
    """Digest the complete authority closure that can affect one task."""

    tree = load_canonical_plan_tree(root, plan_id, state=state)
    tasks = tree["tasks"]
    try:
        task = tasks[task_id]
    except KeyError as error:
        raise SystemExit(
            f"Canonical plan {plan_id} does not contain task {task_id}"
        ) from error

    phase_id = str(task.get("phase_id") or "")
    if phase_id not in tree["phases"]:
        raise SystemExit(
            f"Canonical task {task_id} has no owning phase in plan {plan_id}"
        )

    dependencies: set[str] = set()
    visiting: set[str] = set()

    def visit(current_id: str) -> None:
        if current_id in visiting:
            raise SystemExit(
                f"Task authority dependency cycle reaches {current_id}"
            )
        visiting.add(current_id)
        current = tasks[current_id]
        raw_dependencies = current.get("depends_on")
        if not isinstance(raw_dependencies, list):
            raise SystemExit(f"Canonical task depends_on is invalid: {current_id}")
        for dependency_id in map(str, raw_dependencies):
            if dependency_id not in tasks:
                raise SystemExit(
                    f"Task authority dependency is not canonical: {dependency_id}"
                )
            if dependency_id not in dependencies:
                visit(dependency_id)
                dependencies.add(dependency_id)
        visiting.remove(current_id)

    visit(task_id)
    anchors = {"workspace_root": root.expanduser().resolve()}
    catalog = load_catalog(CURRENT_PLAN_CATALOG)
    specification_id = str(tree["root"].get("source_spec_id") or "")
    specification_records: list[dict[str, Any]] = []
    for specification_state in ("active", "archived"):
        specification_path = canonical_artifact_path(
            family_policy(catalog, "specification"), anchors,
            identity=specification_id, state=specification_state,
        )
        if specification_path.is_file():
            specification_records.append(
                read_artifact(
                    CURRENT_PLAN_CATALOG, "specification", anchors,
                    identity=specification_id, state=specification_state,
                )
            )
    if len(specification_records) != 1:
        raise SystemExit(
            f"Task authority requires one canonical specification: {specification_id}"
        )

    def write_paths(value: Mapping[str, object]) -> list[str]:
        files = value.get("files")
        if isinstance(files, Mapping) and isinstance(files.get("write"), list):
            return sorted(map(str, files["write"]))
        raw = value.get("target_files")
        return sorted(map(str, raw)) if isinstance(raw, list) else []

    def overlaps(left: str, right: str) -> bool:
        left = left.removesuffix("/**").rstrip("/")
        right = right.removesuffix("/**").rstrip("/")
        return left == right or left.startswith(right + "/") or right.startswith(left + "/")

    closure_seed_ids = {task_id, *dependencies}
    closure_paths = [
        path for current_id in closure_seed_ids for path in write_paths(tasks[current_id])
    ]
    closure_interface_values = {
        str(value)
        for current_id in closure_seed_ids
        for values in (
            tasks[current_id].get("interfaces", {}).values()
            if isinstance(tasks[current_id].get("interfaces"), Mapping) else []
        )
        if isinstance(values, list)
        for value in values
    }
    closure_sources = {
        str(source_id)
        for current_id in closure_seed_ids
        for source_id in tasks[current_id].get("source_ids", [])
    }
    shared_records: list[dict[str, object]] = []
    for peer_id, peer in sorted(tasks.items()):
        if peer_id in closure_seed_ids:
            continue
        peer_paths = write_paths(peer)
        peer_interfaces = peer.get("interfaces") if isinstance(peer.get("interfaces"), Mapping) else {}
        peer_interface_values = {
            str(value)
            for values in peer_interfaces.values()
            if isinstance(values, list)
            for value in values
        }
        peer_sources = set(map(str, peer.get("source_ids", [])))
        if not (
            any(overlaps(left, right) for left in closure_paths for right in peer_paths)
            or closure_interface_values.intersection(peer_interface_values)
            or closure_sources.intersection(peer_sources)
        ):
            continue
        shared_records.append(
            {
                "id": peer_id,
                "source_ids": sorted(peer_sources),
                "write_paths": peer_paths,
                "interfaces": peer_interfaces,
            }
        )

    accepted_policy = family_policy(catalog, "accepted-task-result")
    accepted_dependencies: list[dict[str, object]] = []
    for dependency_id in sorted(dependencies):
        probe = canonical_artifact_path(
            accepted_policy, anchors, identity="accepted-probe", state="active",
            bindings={"plan": plan_id, "task": dependency_id},
        )
        records: list[dict[str, Any]] = []
        if probe.parent.is_dir():
            for candidate in sorted(probe.parent.iterdir()):
                if not candidate.is_file() or not candidate.name.endswith(
                    ".accepted-task-result.yaml"
                ):
                    continue
                candidate_data = read_yaml_mapping(candidate)
                candidate_id = str(candidate_data.get("id") or "")
                if not candidate_id:
                    continue
                canonical = canonical_artifact_path(
                    accepted_policy, anchors, identity=candidate_id, state="active",
                    bindings={"plan": plan_id, "task": dependency_id},
                )
                if canonical.resolve() != candidate.resolve():
                    continue
                records.append(
                    read_artifact(
                        CURRENT_PLAN_CATALOG, "accepted-task-result", anchors,
                        identity=candidate_id, state="active",
                        bindings={"plan": plan_id, "task": dependency_id},
                    )
                )
        if len(records) > 1:
            raise SystemExit(
                f"Task authority requires at most one active accepted dependency result: {dependency_id}"
            )
        accepted_dependencies.append(
            {
                "task_id": dependency_id,
                "accepted_result": (
                    {"id": records[0]["data"]["id"], "sha256": records[0]["digest"]}
                    if records else None
                ),
            }
        )

    closure_task_ids = closure_seed_ids
    shared_task_ids = {str(record["id"]) for record in shared_records}
    authority_task_ids = closure_task_ids | shared_task_ids
    phase_ids = {
        str(tasks[current_id].get("phase_id") or "")
        for current_id in closure_task_ids
    }
    source_ids = {
        str(source_id)
        for current_id in authority_task_ids
        for source_id in tasks[current_id].get("source_ids", [])
    }
    root_value = tree["root"]
    source_ids.update(_global_source_ids(root_value.get("authority")))
    source_ids.update(_global_source_ids(root_value.get("strategy")))
    validation_ids = set().union(
        *(_validation_ids(tasks[current_id]) for current_id in closure_task_ids)
    )
    allocated_sources, allocated_validations = _applicable_root_allocations(
        root_value, task_ids=closure_task_ids, phase_ids=phase_ids
    )
    source_ids.update(allocated_sources)
    validation_ids.update(allocated_validations)
    specification_record = specification_records[0]
    specification_sources = _specification_source_records(
        str(specification_record.get("body") or ""),
        specification_record["data"].get("source_knowledge"),
    )
    missing_sources = sorted(source_ids.difference(specification_sources))
    if missing_sources:
        raise SystemExit(
            "Task authority source IDs are not defined by the canonical specification: "
            + ", ".join(missing_sources)
        )

    members: list[dict[str, object]] = [
        {
            "family": "specification",
            "id": specification_id,
            "sources": [
                {"source_id": source_id, "semantic": specification_sources[source_id]}
                for source_id in sorted(source_ids)
            ],
        },
        {
            "family": "root-plan",
            "id": plan_id,
            "value": _root_authority_projection(
                root_value,
                source_ids=source_ids,
                task_ids=closure_task_ids,
                phase_ids=phase_ids,
                validation_ids=validation_ids,
            ),
        },
        {
            "family": "phase",
            "id": phase_id,
            "value": _phase_authority_projection(
                tree["phases"][phase_id],
                source_ids=source_ids,
                task_ids=closure_task_ids,
                validation_ids=validation_ids,
            ),
        },
    ]
    dependency_phase_ids = phase_ids - {phase_id}
    members.extend(
        {
            "family": "dependency-phase",
            "id": dependency_phase_id,
            "value": _phase_authority_projection(
                tree["phases"][dependency_phase_id],
                source_ids=source_ids,
                task_ids=closure_task_ids,
                validation_ids=validation_ids,
            ),
        }
        for dependency_phase_id in sorted(dependency_phase_ids)
    )
    members.extend(
        {
            "family": "dependency-task",
            "id": dependency_id,
            "value": canonical_yaml_plan_value(tasks[dependency_id]),
        }
        for dependency_id in sorted(dependencies)
    )
    members.append(
        {
            "family": "task",
            "id": task_id,
            "value": canonical_yaml_plan_value(task),
        }
    )
    payload = {
        "projection_schema": CANONICAL_TASK_AUTHORITY_PROJECTION_SCHEMA,
        "members": members,
        "accepted_dependencies": accepted_dependencies,
        "shared_authority_records": shared_records,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {"id": task_id, "sha256": hashlib.sha256(encoded).hexdigest()}


def canonical_task_data(root: Path, plan_id: str, task_id: str) -> dict[str, Any]:
    tree = load_canonical_plan_tree(root, plan_id)
    try:
        return dict(tree["tasks"][task_id])
    except KeyError as error:
        raise SystemExit(
            f"Canonical plan {plan_id} does not contain task {task_id}"
        ) from error


def source_obligation_records(
    data: Mapping[str, object], *, label: str = "Task"
) -> dict[str, str]:
    """Validate the mechanical binding between task source IDs and supplied semantics."""

    raw_source_ids = data.get("source_ids")
    if not isinstance(raw_source_ids, list):
        raise SystemExit(f"{label} requires source_ids")
    source_ids = [str(value) for value in raw_source_ids]
    obligations = data.get("source_obligations")
    if not isinstance(obligations, list):
        raise SystemExit(f"{label} requires source_obligations")
    records: dict[str, str] = {}
    for item in obligations:
        if not isinstance(item, dict):
            raise SystemExit(f"{label} source_obligations entries must be mappings")
        source_id = str(item.get("source_id") or "")
        semantic = item.get("semantic")
        if source_id in records:
            raise SystemExit(f"{label} source_obligations duplicate source_id: {source_id}")
        if not isinstance(semantic, str) or not semantic.strip():
            raise SystemExit(f"{label} source_obligations require non-empty semantic values")
        records[source_id] = semantic.strip()
    if set(records) != set(source_ids) or len(records) != len(source_ids):
        raise SystemExit(f"{label} source_obligations must exactly bind source_ids")
    return records
