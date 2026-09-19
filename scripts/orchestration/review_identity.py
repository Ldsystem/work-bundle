"""Versioned structural identity projections for orchestration plan artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from artifact_store import (
    canonical_artifact_path,
    family_policy,
    load_catalog,
    read_artifact,
    read_yaml_mapping,
)


CANONICAL_YAML_PLAN_PROJECTION_SCHEMA = "canonical-yaml-plan-tree-v1"
CURRENT_PLAN_CATALOG = (
    Path(__file__).resolve().parents[2]
    / "references/assets/orchestration/contract/artifact-family-catalog-v5.yaml"
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
