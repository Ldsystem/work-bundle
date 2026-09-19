#!/usr/bin/env python3
"""Current Stage 5 review, accepted-result, and final-review adapters."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from artifact_store import (
    canonical_artifact_path, family_policy, load_catalog, read_artifact,
    read_yaml_mapping, rebuild_index,
)
from core import now_date, resolve_workspace_root
from review_identity import (
    canonical_plan_tree_identity,
    canonical_task_data,
    load_canonical_plan_tree,
)


CURRENT_CATALOG = Path(__file__).resolve().parents[2] / "references/assets/orchestration/contract/artifact-family-catalog-v5.yaml"
CURRENT_FAMILIES = {"implementation-review", "accepted-task-result", "final-workflow-review"}
CURRENT_STRUCTURAL_FIELDS = {
    "artifact_type", "schema_version", "id", "plan_id", "task_id",
    "target_sha256", "product_sha256", "knowledge_action", "date_created", "last_updated",
}


def plan_review_identity(root: Path, plan_path: Path, *, content: str | None = None) -> dict[str, Any]:
    """Digest one canonical, schema-valid plan tree."""

    plan_root = root / ".work-bundle/orchestration/plan"
    if not plan_path.resolve().is_relative_to(plan_root.resolve()):
        raise SystemExit("plan identity path escapes the canonical plan store")
    if content is not None:
        raise SystemExit("plan identity requires canonical stored authority")
    root_data = read_yaml_mapping(plan_path)
    plan_id = str(root_data.get("id") or "")
    tree = load_canonical_plan_tree(root, plan_id)
    lifecycle = str(tree["state"])
    expected = canonical_artifact_path(
        _policy("root-plan"),
        {"workspace_root": root},
        identity=plan_id,
        state=lifecycle,
    )
    if expected.resolve() != plan_path.resolve():
        raise SystemExit("plan identity requires the canonical root plan path")
    return canonical_plan_tree_identity(root, plan_id, state=lifecycle)


def _workspace(args: argparse.Namespace) -> Path:
    return resolve_workspace_root(args)


def _anchors(args: argparse.Namespace) -> dict[str, Path]:
    return {"workspace_root": _workspace(args)}


def _policy(family: str) -> dict[str, Any]:
    if family not in CURRENT_FAMILIES and family not in {
        "executor-result", "root-plan", "phase", "task"
    }:
        raise SystemExit(f"Unsupported current review family: {family}")
    return family_policy(load_catalog(CURRENT_CATALOG), family)


def _semantic_input(args: argparse.Namespace, family: str) -> dict[str, Any]:
    data = read_yaml_mapping(Path(str(args.content_file)))
    overrides = sorted(CURRENT_STRUCTURAL_FIELDS.intersection(data))
    if overrides:
        raise SystemExit(f"{family} semantic input contains structural field override: " + ", ".join(overrides))
    return data


def _bindings(family: str, *, plan_id: str, task_id: str | None = None) -> dict[str, str]:
    result = {"plan": plan_id}
    if family == "accepted-task-result" or (family == "implementation-review" and task_id):
        if not task_id:
            raise SystemExit(f"{family} requires task binding")
        result["task"] = task_id
    return result


def _available(args: argparse.Namespace, family: str, bindings: Mapping[str, str]) -> None:
    policy = _policy(family)
    for state in policy["lifecycle"]["states"]:
        if canonical_artifact_path(policy, _anchors(args), identity=str(args.id), state=str(state), bindings=bindings).exists():
            raise SystemExit(f"{family} canonical identity collision: {args.id}")


def _write(args: argparse.Namespace, family: str, data: Mapping[str, Any], bindings: Mapping[str, str]) -> dict[str, Any]:
    from artifact_store import write_artifact

    _available(args, family, bindings)
    today = now_date()
    schema_id = str(_policy(family)["schema"]["id"])
    try:
        schema_version = int(schema_id.rsplit("-v", 1)[1])
    except (IndexError, ValueError) as error:
        raise SystemExit(f"Current {family} schema has no numeric version: {schema_id}") from error
    document = {
        **dict(data), "artifact_type": family, "schema_version": schema_version,
        "id": str(args.id), "plan_id": str(args.plan_id),
        "task_id": getattr(args, "task_id", None), "date_created": today, "last_updated": today,
    }
    if family == "final-workflow-review":
        document.pop("task_id", None)
    return write_artifact(CURRENT_CATALOG, family, _anchors(args), document, state="active", bindings=bindings)


def _validate_plan_authority(args: argparse.Namespace, data: Mapping[str, Any]) -> dict[str, Any]:
    plan_id = str(args.plan_id)
    current = canonical_plan_tree_identity(_workspace(args), plan_id)
    supplied = data.get("plan_identity")
    tree = load_canonical_plan_tree(_workspace(args), plan_id)
    if (
        not isinstance(supplied, dict)
        or supplied != current
        or data.get("specification_id") != tree["root"].get("source_spec_id")
    ):
        raise SystemExit("plan/specification identity is stale")
    return tree


def _rows(args: argparse.Namespace, family: str) -> list[dict[str, Any]]:
    result = rebuild_index(CURRENT_CATALOG, family, _anchors(args))
    rows = [json.loads(line) for line in Path(str(result["path"])).read_text(encoding="utf-8").splitlines() if line]
    plan_id, task_id = getattr(args, "plan_id", None), getattr(args, "task_id", None)
    return [row for row in rows if (not plan_id or row.get("plan_id") == plan_id) and (not task_id or row.get("task_id") == task_id)]


def _reference(args: argparse.Namespace, family: str, identity: str, bindings: Mapping[str, str]) -> dict[str, Any]:
    matches = []
    for state in _policy(family)["lifecycle"]["states"]:
        path = canonical_artifact_path(_policy(family), _anchors(args), identity=identity, state=str(state), bindings=bindings)
        if path.is_file():
            matches.append(read_artifact(CURRENT_CATALOG, family, _anchors(args), identity=identity, state=str(state), bindings=bindings))
    if len(matches) != 1:
        raise SystemExit(f"Current {family} reference is not canonical: {identity}")
    return matches[0]


def _candidate_validator():
    path = Path(__file__).resolve().parents[1] / "work-bundle/reviewer_workspace.py"
    spec = importlib.util.spec_from_file_location("_wb_current_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load exact-candidate validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_implementation_review(args: argparse.Namespace) -> dict[str, Any]:
    data = _semantic_input(args, "implementation-review")
    _validate_plan_authority(args, data)
    reviewer = data.get("reviewer")
    if not isinstance(reviewer, dict) or set(reviewer) != {"agent_id"}:
        raise SystemExit("Implementation review requires one concrete reviewer identity")
    implementor = str(data.get("implementor_agent_id") or "")
    source_root = Path(str(getattr(args, "source_root", "") or ""))
    if not implementor or not str(reviewer.get("agent_id") or "") or not source_root:
        raise SystemExit("Implementation review requires concrete source, implementor, and reviewer identities")
    try:
        checked = _candidate_validator().validate_current_candidate_and_independence(
            source_root, data.get("target"),
            reviewer_agent_id=str(reviewer["agent_id"]), implementor_agent_id=implementor,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    data["target"] = checked["target"]
    data["target_sha256"] = checked["target"]["sha256"]
    if data.get("scope") == "task" and not getattr(args, "task_id", None):
        raise SystemExit("Task implementation review requires task binding")
    return _write(args, "implementation-review", data, _bindings("implementation-review", plan_id=str(args.plan_id), task_id=getattr(args, "task_id", None)))


def list_implementation_reviews(args: argparse.Namespace) -> list[dict[str, Any]]:
    return _rows(args, "implementation-review")


def write_accepted_task_result(args: argparse.Namespace) -> dict[str, Any]:
    data = _semantic_input(args, "accepted-task-result")
    product, executor, review, knowledge = (data.get(key) for key in ("product_identity", "executor_result", "implementation_review", "knowledge_disposition"))
    if not all(isinstance(value, dict) for value in (product, executor, knowledge)):
        raise SystemExit("Accepted task result requires canonical product, executor, and knowledge facts")
    task = canonical_task_data(_workspace(args), str(args.plan_id), str(args.task_id))
    acceptance_review = task.get("acceptance_review")
    required = acceptance_review.get("required") if isinstance(acceptance_review, dict) else None
    if type(required) is not bool:
        raise SystemExit("Canonical task acceptance_review.required must be boolean")
    if required and review is None:
        raise SystemExit("Canonical task requires an implementation review")
    executor_record = _reference(args, "executor-result", str(executor.get("id")), {"plan": str(args.plan_id), "task": str(args.task_id)})
    if executor_record["digest"] != executor.get("sha256"):
        raise SystemExit("Accepted task result executor digest mismatch")
    if review is not None:
        if not isinstance(review, dict):
            raise SystemExit("Accepted task result implementation review reference is invalid")
        reviewed = _reference(args, "implementation-review", str(review.get("id")), _bindings("implementation-review", plan_id=str(args.plan_id), task_id=str(args.task_id)))
        if reviewed["digest"] != review.get("sha256") or reviewed["data"].get("verdict") != "accept":
            raise SystemExit("Accepted task result requires an exact accept implementation review")
        if reviewed["data"].get("target_sha256") != product.get("sha256"):
            raise SystemExit("Accepted task result product identity does not match review target")
    data["product_sha256"] = product.get("sha256")
    data["knowledge_action"] = knowledge.get("action")
    return _write(args, "accepted-task-result", data, _bindings("accepted-task-result", plan_id=str(args.plan_id), task_id=str(args.task_id)))


def list_accepted_task_results(args: argparse.Namespace) -> list[dict[str, Any]]:
    return _rows(args, "accepted-task-result")


def write_final_workflow_review(args: argparse.Namespace) -> dict[str, Any]:
    data = _semantic_input(args, "final-workflow-review")
    _validate_plan_authority(args, data)
    candidate = data.get("candidate_identity")
    if not isinstance(candidate, dict) or not isinstance(candidate.get("sha256"), str):
        raise SystemExit("Final workflow review requires exact candidate identity")
    seen_tasks: set[str] = set()
    for reference in data.get("accepted_results", []):
        if not isinstance(reference, dict) or not str(reference.get("task_id") or ""):
            raise SystemExit("Final workflow review contains invalid accepted-result reference")
        task_id = str(reference["task_id"])
        if task_id in seen_tasks:
            raise SystemExit("Final workflow review duplicates an accepted task")
        seen_tasks.add(task_id)
        accepted = _reference(
            args, "accepted-task-result", str(reference.get("id")),
            {"plan": str(args.plan_id), "task": task_id},
        )
        if accepted["digest"] != reference.get("sha256"):
            raise SystemExit("Final workflow review accepted-result digest mismatch")
    for reference in data.get("accepted_reviews", []):
        reviewed = _reference(args, "implementation-review", str(reference.get("id")), {"plan": str(args.plan_id)})
        if reviewed["digest"] != reference.get("sha256") or reviewed["data"].get("verdict") != "accept":
            raise SystemExit("Final workflow review requires exact accepted implementation reviews")
    data["target_sha256"] = candidate["sha256"]
    return _write(args, "final-workflow-review", data, _bindings("final-workflow-review", plan_id=str(args.plan_id)))


def list_final_workflow_reviews(args: argparse.Namespace) -> list[dict[str, Any]]:
    return _rows(args, "final-workflow-review")


def cmd_write_implementation_review(args: argparse.Namespace) -> None:
    print(json.dumps(write_implementation_review(args), ensure_ascii=False, sort_keys=True))


def cmd_list_implementation_reviews(args: argparse.Namespace) -> None:
    for row in list_implementation_reviews(args): print(json.dumps(row, ensure_ascii=False, sort_keys=True))


def cmd_write_accepted_task_result(args: argparse.Namespace) -> None:
    print(json.dumps(write_accepted_task_result(args), ensure_ascii=False, sort_keys=True))


def cmd_list_accepted_task_results(args: argparse.Namespace) -> None:
    for row in list_accepted_task_results(args): print(json.dumps(row, ensure_ascii=False, sort_keys=True))


def cmd_write_final_workflow_review(args: argparse.Namespace) -> None:
    print(json.dumps(write_final_workflow_review(args), ensure_ascii=False, sort_keys=True))


def cmd_list_final_workflow_reviews(args: argparse.Namespace) -> None:
    for row in list_final_workflow_reviews(args): print(json.dumps(row, ensure_ascii=False, sort_keys=True))
