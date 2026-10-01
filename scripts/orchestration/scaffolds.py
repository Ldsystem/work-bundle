"""Read-only, explicitly supported semantic inputs for current artifact writers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from artifact_store import canonical_artifact_path, family_policy, load_catalog, read_artifact
from core import resolve_workspace_root
from review_identity import _specification_source_records, load_canonical_plan_tree


# Deliberate feature boundary: adding a catalog family does not add a scaffold.
SUPPORTED_FAMILIES = {
    "specification-v1": ("specification", "write-spec"),
    "plan-v1": ("root-plan", "write-plan"),
    "phase-v2": ("phase", "write-phase"),
    "task-v3": ("task", "write-task"),
    "executor-result-v2": ("executor-result", "write-executor-result"),
    "implementation-review-v3": ("implementation-review", "write-implementation-review"),
    "accepted-task-result-v2": ("accepted-task-result", "write-accepted-task-result"),
    "final-workflow-review-v1": ("final-workflow-review", "write-final-workflow-review"),
}
CATALOG = Path(__file__).resolve().parents[2] / "references/assets/orchestration/contract/artifact-family-catalog-v7.yaml"


def _placeholder(field: str) -> str:
    return f"<agent-authored-{field.replace('_', '-')}>"


def _semantic_shell(family: str) -> dict[str, Any]:
    # Only writer-permitted semantic keys. Collection placeholders require an
    # explicit caller decision even when an empty collection would be valid.
    fields = {
        "specification": "project source_knowledge related_handoffs tags execution_workspace",
        "root-plan": "source_coverage authority strategy phase_index dependency_graph risks validation_strategy completion_criteria knowledge_base_update semantic_loop execution_workspace",
        "phase": "order source_ids depends_on task_index barriers validation completion_criteria allocated_rules allocated_skills delivery",
        "task": "order task_type source_ids source_obligations truth_basis depends_on source_files target_files target_symbols interfaces steps validation evidence_capability completion_criteria methodology executor_profile acceptance_review allocated_rules allocated_skills handoff_contract",
        "executor-result": "result_state summary changes validation_observations unresolved_product_blockers task_fit repository_observations codegraph_observations delegation knowledge_disposition",
        "implementation-review": "scope specification_id authority_identity target implementor_agent_id reviewer reviewed_obligations focused_observations verdict findings",
        "accepted-task-result": "product_identity executor_result implementation_review validation_outcomes unresolved_material_defects knowledge_disposition",
        "final-workflow-review": "specification_id plan_identity candidate_identity coverage accepted_results accepted_reviews test_outcomes unresolved_material_defects knowledge_disposition knowledge_return repository_finalization verdict archive_ready reasons",
    }
    semantic = {field: _placeholder(field) for field in fields[family].split()}
    if family == "implementation-review":
        # Expose the persisted target shape as editable input, never compute a
        # candidate or infer review/acceptance from canonical reference facts.
        semantic["target"] = {
            "kind": _placeholder("kind"),
            "base_commit": "<agent-authored-candidate-commit-or-worktree-baseline>",
            "manifest": _placeholder("manifest"),
            "sha256": _placeholder("sha256"),
        }
    return semantic


def _structural_fields(family: str) -> set[str]:
    # The actual readers are the restriction owners.
    if family == "specification":
        from specs import STRUCTURAL_INPUT_FIELDS
        return set(STRUCTURAL_INPUT_FIELDS)
    if family in {"root-plan", "phase", "task"}:
        from plans import PLAN_STRUCTURAL_INPUT_FIELDS, PHASE_STRUCTURAL_INPUT_FIELDS, TASK_STRUCTURAL_INPUT_FIELDS
        return set({"root-plan": PLAN_STRUCTURAL_INPUT_FIELDS,
                    "phase": PHASE_STRUCTURAL_INPUT_FIELDS, "task": TASK_STRUCTURAL_INPUT_FIELDS}[family])
    if family == "executor-result":
        from handoffs import STRUCTURAL_FIELDS
        return set(STRUCTURAL_FIELDS)
    from review_runtime import CURRENT_STRUCTURAL_FIELDS
    return set(CURRENT_STRUCTURAL_FIELDS) | ({"authority_identity"} if family == "accepted-task-result" else set())


def build_scaffold(args: argparse.Namespace) -> dict[str, Any]:
    requested = str(args.family)
    if requested not in SUPPORTED_FAMILIES:
        raise SystemExit(f"Unsupported scaffold family: {requested}")
    family, command = SUPPORTED_FAMILIES[requested]
    root = resolve_workspace_root(args)
    anchors = {"workspace_root": root}
    catalog = load_catalog(CATALOG)
    policy = family_policy(catalog, family)
    if policy["schema"]["id"] != requested:
        raise SystemExit(f"Scaffold requires its explicit supported schema: {requested}")
    allowed = set() if family in {"phase", "task"} else {"id"}
    if family in {"specification", "root-plan", "phase", "task"}:
        allowed.add("title")
    if family in {"phase", "task"}:
        allowed.add("status")
    if family in {"specification", "root-plan"}:
        allowed.update({"purpose", "component", "version", "status"})
    if family != "specification":
        allowed.add("source_spec_id")
    if family not in {"specification", "root-plan"}:
        allowed.add("plan_id")
    if family in {"phase", "task", "executor-result"}:
        allowed.add("phase_id")
    if family in {"task", "executor-result", "implementation-review", "accepted-task-result"}:
        allowed.add("task_id")
    if family == "implementation-review":
        allowed.add("source_root")
    options = {"id", "title", "purpose", "component", "version", "status",
               "source_spec_id", "plan_id", "phase_id", "task_id", "source_root"}
    supplied = {key: getattr(args, key, None) for key in options if getattr(args, key, None) is not None}
    unexpected = sorted(set(supplied) - allowed)
    if unexpected:
        raise SystemExit("Unsupported scaffold invocation binding: " + ", ".join(unexpected))
    invocation = dict(supplied)
    context: dict[str, Any] = {"source_ids": []}
    source_spec_id = supplied.get("source_spec_id")
    task = None
    if family not in {"specification", "root-plan"}:
        plan_id = supplied.get("plan_id")
        if not plan_id:
            raise SystemExit(f"{requested} requires --plan-id")
        from plans import _active_root_plan
        plan = _active_root_plan(args, str(plan_id))
        if source_spec_id and source_spec_id != plan["source_spec_id"]:
            raise SystemExit("Scaffold source specification binding does not match canonical plan")
        source_spec_id = plan["source_spec_id"]
        context["plan"] = {"id": plan_id, "source_spec_id": source_spec_id}
        if family == "task":
            phase_id = supplied.get("phase_id")
            if not phase_id:
                raise SystemExit("task-v3 requires --phase-id")
            parent = read_artifact(CATALOG, "phase", anchors, identity=str(phase_id),
                                   state="active", bindings={"plan": str(plan_id)})
            context["phase"] = {"id": phase_id, "artifact": str(parent["path"])}
        if family in {"executor-result", "implementation-review", "accepted-task-result"}:
            task_id = supplied.get("task_id")
            if family != "implementation-review" and not task_id:
                raise SystemExit(f"{requested} requires --task-id")
            if task_id:
                tree = load_canonical_plan_tree(root, str(plan_id), state="active")
                task = tree["tasks"].get(str(task_id))
                if task is None:
                    raise SystemExit(f"Unknown canonical task binding: {task_id}")
                phase_id = task["phase_id"]
                if supplied.get("phase_id") and supplied["phase_id"] != phase_id:
                    raise SystemExit("Scaffold phase binding does not match canonical task")
                context["task"] = {"id": task_id, "phase_id": phase_id}
                if family == "executor-result":
                    invocation["phase_id"] = phase_id
                    context["delivery_task"] = tree["phases"][phase_id].get("delivery", {}).get("task_id") == task_id
    source_ids = list(getattr(args, "source_id", []) or [])
    if len(source_ids) != len(set(source_ids)):
        raise SystemExit("Duplicate scaffold source ID")
    if family == "root-plan" and not source_spec_id:
        raise SystemExit("plan-v1 requires --source-spec-id")
    if source_ids and not source_spec_id:
        raise SystemExit("Scaffold source IDs require a canonical source specification")
    if source_spec_id:
        source = read_artifact(CATALOG, "specification", anchors, identity=str(source_spec_id), state="active")
        if source["data"]["status"] != "verified":
            raise SystemExit("Scaffold source specification must be active and verified")
        records = _specification_source_records(str(source["body"]), source["data"].get("source_knowledge"))
        unknown = sorted(set(source_ids) - set(records))
        if unknown:
            raise SystemExit("Unknown source ID: " + ", ".join(unknown))
        context["specification"] = {"id": source_spec_id, "artifact": str(source["path"]),
                                    "status": "verified", "sha256": source["digest"]}
        context["source_ids"] = [{"id": source_id, "artifact": str(source["path"]),
                                   "status": "verified", "semantic": records[source_id]}
                                  for source_id in source_ids]
    # Use the store's identity/path checker without creating any path or index.
    identity = (supplied.get("task_id") if family == "task" else supplied.get("phase_id")
                if family == "phase" else supplied.get("id"))
    bindings = {key: str(value) for key, value in {
        "plan": supplied.get("plan_id"), "phase": supplied.get("phase_id"),
        "task": supplied.get("task_id"), "source_spec": source_spec_id,
    }.items() if value is not None}
    relevant = {item["name"] for item in policy["relationships"]["bindings"]}
    canonical_artifact_path(policy, anchors, identity=str(identity or {
        "specification": "spec-placeholder", "root-plan": "plan-placeholder", "phase": "phase-placeholder",
        "task": "task-placeholder", "executor-result": "result-placeholder", "implementation-review": "review-placeholder",
        "accepted-task-result": "accepted-placeholder", "final-workflow-review": "final-placeholder",
    }[family]), state="active", bindings={key: value for key, value in bindings.items() if key in relevant})
    if supplied.get("source_root"):
        if not Path(str(supplied["source_root"])).expanduser().is_dir():
            raise SystemExit("Scaffold source-root must be an existing repository directory")
    if supplied.get("status"):
        from specs import QUALIFICATION_STATUSES
        from plans import PLAN_QUALIFICATION_STATUSES, PLANNED_STATUS
        statuses = ({PLANNED_STATUS} if family in {"phase", "task"} else
                    QUALIFICATION_STATUSES if family == "specification" else PLAN_QUALIFICATION_STATUSES - {"verified"})
        if supplied["status"] not in statuses:
            raise SystemExit("Unsupported writer qualification status")
    if source_spec_id and family != "root-plan":
        invocation.pop("source_spec_id", None)  # Resolution-only option, absent from these writers.
    for key in allowed - {"source_spec_id", "source_root"}:
        if key == "status" and family in {"phase", "task"} and key not in supplied:
            continue  # Preserve the existing writer default when omitted.
        invocation.setdefault(key, _placeholder(key))
    if family == "root-plan":
        invocation["source_spec_id"] = source_spec_id
    if family == "implementation-review":
        invocation.setdefault("source_root", _placeholder("source_root"))
        if not supplied.get("task_id"):
            invocation.pop("task_id", None)
    semantic = _semantic_shell(family)
    if family in {"phase", "task"} and source_ids:
        semantic["source_ids"] = source_ids
    if family == "task" and source_ids:
        semantic["source_obligations"] = [{"source_id": item, "semantic": "<agent-authored-obligation>"} for item in source_ids]
    if family == "executor-result" and context.get("delivery_task"):
        semantic["phase_handoff"] = _placeholder("phase_handoff")
    result = {"artifact_family": requested, "writer_command": command,
              "invocation_inputs": invocation, "semantic_input": semantic,
              "resolved_context": context, "script_owned_fields": sorted(_structural_fields(family))}
    if family == "specification":
        result["semantic_body"] = "<agent-authored-specification-body>"
    return result


def cmd_scaffold(args: argparse.Namespace) -> None:
    print(json.dumps(build_scaffold(args), ensure_ascii=False, indent=2, sort_keys=True))
