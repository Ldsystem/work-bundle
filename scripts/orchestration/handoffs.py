"""Current schema-owned executor-result storage.

Executor results are factual continuation records. They do not contain or
infer product-review verdicts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core import now_date, resolve_workspace_root
from artifact_store import (
    canonical_artifact_path,
    family_policy,
    load_catalog,
    read_artifact,
    read_yaml_mapping,
    rebuild_index,
    transition_artifact,
    write_artifact,
)


CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "references/assets/orchestration/contract/artifact-family-catalog-v4.yaml"
)
FAMILY = "executor-result"
STRUCTURAL_FIELDS = {
    "artifact_type", "schema_version", "id", "plan_id", "phase_id", "task_id",
    "date_created", "last_updated",
}
FORBIDDEN_SEMANTIC_FIELDS = {
    "verdict", "review", "review_receipt", "publication", "accepted_result",
    "final_audit", "recommended_repair", "knowledge_write_authorization",
}


def _anchors(args: argparse.Namespace) -> dict[str, Path]:
    return {"workspace_root": resolve_workspace_root(args)}


def _policy() -> dict[str, Any]:
    return family_policy(load_catalog(CATALOG_PATH), FAMILY)


def _read_compact_yaml_metadata(path: Path) -> dict[str, object]:
    """Maintained YAML parsing retained for non-current read-only callers."""

    return read_yaml_mapping(path)


def _semantic_input(path: Path) -> dict[str, Any]:
    data = read_yaml_mapping(path)
    overrides = sorted(STRUCTURAL_FIELDS.intersection(data))
    forbidden = sorted(FORBIDDEN_SEMANTIC_FIELDS.intersection(data))
    if overrides:
        raise SystemExit(
            "Executor-result semantic input contains structural field override: "
            + ", ".join(overrides)
        )
    if forbidden:
        raise SystemExit(
            "Executor-result semantic input contains forbidden field: "
            + ", ".join(forbidden)
        )
    return data


def _bindings(args: argparse.Namespace) -> dict[str, str]:
    return {"plan": str(args.plan_id), "task": str(args.task_id)}


def _active_result_or_none(args: argparse.Namespace) -> dict[str, Any] | None:
    policy = _policy()
    active = canonical_artifact_path(
        policy,
        _anchors(args),
        identity=str(args.id),
        state="active",
        bindings=_bindings(args),
    )
    if active.is_file():
        return read_artifact(
            CATALOG_PATH, FAMILY, _anchors(args), identity=str(args.id),
            state="active", bindings=_bindings(args),
        )
    for state in policy["lifecycle"]["states"]:
        if state == "active":
            continue
        target = canonical_artifact_path(
            policy,
            _anchors(args),
            identity=str(args.id),
            state=str(state),
            bindings=_bindings(args),
        )
        if target.exists():
            raise SystemExit(f"Executor-result canonical identity collision: {args.id}")
    return None


def write_executor_result(args: argparse.Namespace) -> dict[str, Any]:
    semantic = _semantic_input(Path(str(args.content_file)))
    existing = _active_result_or_none(args)
    today = now_date()
    data = {
        **semantic,
        "artifact_type": FAMILY,
        "schema_version": 1,
        "id": str(args.id),
        "plan_id": str(args.plan_id),
        "phase_id": getattr(args, "phase_id", None),
        "task_id": str(args.task_id),
        "date_created": str(existing["data"]["date_created"]) if existing else today,
        "last_updated": today,
    }
    return write_artifact(
        CATALOG_PATH,
        FAMILY,
        _anchors(args),
        data,
        state="active",
        bindings=_bindings(args),
    )


def _index_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    result = rebuild_index(CATALOG_PATH, FAMILY, _anchors(args))
    path = Path(str(result["path"]))
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def list_executor_results(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = _index_rows(args)
    plan_id = getattr(args, "plan_id", None)
    task_id = getattr(args, "task_id", None)
    return [
        row for row in rows
        if (not plan_id or row.get("plan_id") == plan_id)
        and (not task_id or row.get("task_id") == task_id)
    ]


def cmd_write_executor_result(args: argparse.Namespace) -> None:
    print(json.dumps(write_executor_result(args), ensure_ascii=False, sort_keys=True))


def cmd_list_executor_results(args: argparse.Namespace) -> None:
    for row in list_executor_results(args):
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))


def cmd_transition_executor_result(args: argparse.Namespace) -> None:
    result = transition_artifact(
        CATALOG_PATH,
        FAMILY,
        _anchors(args),
        identity=str(args.id),
        current_state=str(args.current_state),
        target_state=str(args.target_state),
        bindings=_bindings(args),
    )
    rebuild_index(CATALOG_PATH, FAMILY, _anchors(args))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def cmd_index_executor_results(args: argparse.Namespace) -> None:
    print(json.dumps(rebuild_index(CATALOG_PATH, FAMILY, _anchors(args)), sort_keys=True))
