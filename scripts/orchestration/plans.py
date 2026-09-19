import json
import subprocess

from core import *
from execution_context import (
    _iter_task_bindings,
    _persist_binding,
)
from artifact_store import (
    canonical_artifact_path,
    family_policy,
    load_catalog,
    read_artifact,
    read_yaml_mapping,
    rebuild_index,
    validate_artifact,
    write_artifact,
)
from completion_provenance import (
    CompletionProvenanceError,
    ManagedProvenanceStore,
    release_completion_binding,
    validate_execution_binding_ownership,
    validate_ownership_shape,
)
from review_identity import canonical_plan_tree_identity, source_obligation_records






CATALOG_PATH = Path(__file__).resolve().parents[2] / "references/assets/orchestration/contract/artifact-family-catalog-v5.yaml"
PLAN_FAMILIES = ("root-plan", "phase", "task")
PLAN_QUALIFICATION_STATUSES = {"draft", "verified", "superseded"}
PLAN_QUALIFICATION_TRANSITIONS = {
    "draft": {"verified", "superseded"},
    "verified": {"superseded"},
    "superseded": set(),
}
PLANNED_STATUS = "planned"
PLAN_STRUCTURAL_INPUT_FIELDS = {
    "artifact_type", "schema_version", "id", "goal", "purpose", "component",
    "version", "source_spec_id", "status", "date_created", "last_updated",
}
PHASE_STRUCTURAL_INPUT_FIELDS = {
    "artifact_type", "schema_version", "id", "plan_id", "name", "status",
    "date_created", "last_updated",
}
TASK_STRUCTURAL_INPUT_FIELDS = {
    "artifact_type", "schema_version", "id", "plan_id", "phase_id", "name",
    "status", "date_created", "last_updated",
}


def _plan_anchors(args: argparse.Namespace) -> dict[str, Path]:
    return {"workspace_root": resolve_workspace_root(args)}


def _plan_policy(family: str) -> dict[str, object]:
    return family_policy(load_catalog(CATALOG_PATH), family)


def _semantic_yaml(path: Path, forbidden: set[str], label: str) -> dict[str, object]:
    data = read_yaml_mapping(path)
    overrides = sorted(forbidden.intersection(data))
    if overrides:
        raise SystemExit(
            f"{label} semantic input contains structural field override: "
            + ", ".join(overrides)
        )
    return data


def _family_bindings(family: str, row: dict[str, object]) -> dict[str, str]:
    if family == "root-plan":
        return {"source_spec": str(row["source_spec_id"])}
    if family == "phase":
        return {"plan": str(row["plan_id"])}
    return {"plan": str(row["plan_id"]), "phase": str(row["phase_id"])}


def _canonical_row(args: argparse.Namespace, family: str, row: dict[str, object]) -> dict[str, object]:
    identity = str(row["id"])
    bindings = _family_bindings(family, row)
    matches: list[tuple[str, Path]] = []
    for state in ("active", "archived"):
        path = canonical_artifact_path(
            _plan_policy(family), _plan_anchors(args), identity=identity,
            state=state, bindings=bindings,
        )
        if path.is_file():
            matches.append((state, path))
    if len(matches) != 1:
        raise SystemExit(
            f"Planning artifact identity must resolve to one canonical location: {family} {identity}"
        )
    state, path = matches[0]
    stored = read_artifact(
        CATALOG_PATH, family, _plan_anchors(args), identity=identity,
        state=state, bindings=bindings,
    )["data"]
    presentation = dict(stored)
    presentation.update(
        {
            "type": "plan" if family == "root-plan" else family,
            "title": stored.get("goal") or stored.get("name"),
            "path": rel(path, args),
            "state": state,
            "created_at": stored["date_created"],
            "updated_at": stored["last_updated"],
        }
    )
    return presentation


def _index_rows(args: argparse.Namespace, family: str) -> list[dict[str, object]]:
    result = rebuild_index(CATALOG_PATH, family, _plan_anchors(args))
    index_path = Path(str(result["path"]))
    return [
        json.loads(line)
        for line in index_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _identity_collision(
    args: argparse.Namespace,
    family: str,
    identity: str,
    *,
    bindings: dict[str, str] | None = None,
) -> bool:
    policy = _plan_policy(family)
    return any(
        canonical_artifact_path(
            policy,
            _plan_anchors(args),
            identity=identity,
            state=str(state),
            bindings=bindings,
        ).exists()
        for state in policy["lifecycle"]["states"]
    )


def _next_plan_id(args: argparse.Namespace) -> str:
    prefix = f"plan-{now_date().replace('-', '')}-"
    sequence = 1
    while _identity_collision(args, "root-plan", f"{prefix}{sequence:03d}"):
        sequence += 1
    return f"{prefix}{sequence:03d}"


def _validate_candidate(
    family: str, data: dict[str, object], bindings: dict[str, str]
) -> None:
    validate_artifact(
        _plan_policy(family),
        data,
        catalog_path=CATALOG_PATH,
        bindings=bindings,
    )


def _active_root_plan(args: argparse.Namespace, plan_id: str) -> dict[str, object]:
    policy = _plan_policy("root-plan")
    path = canonical_artifact_path(
        policy,
        _plan_anchors(args),
        identity=plan_id,
        state="active",
    )
    if not path.is_file():
        raise SystemExit(f"Root plan is not canonical and active: {plan_id}")
    raw = read_yaml_mapping(path)
    source_spec_id = str(raw.get("source_spec_id") or "")
    if not source_spec_id:
        raise SystemExit(f"Root plan source binding is invalid: {plan_id}")
    return dict(
        read_artifact(
            CATALOG_PATH,
            "root-plan",
            _plan_anchors(args),
            identity=plan_id,
            state="active",
            bindings={"source_spec": source_spec_id},
        )["data"]
    )


def _active_artifact(
    args: argparse.Namespace, family: str, identity: str, bindings: dict[str, str]
) -> dict[str, object]:
    return dict(
        read_artifact(
            CATALOG_PATH, family, _plan_anchors(args), identity=identity,
            state="active", bindings=bindings,
        )["data"]
    )









def index_plans(args: argparse.Namespace) -> list[dict[str, object]]:
    rows = [
        _canonical_row(args, family, row)
        for family in PLAN_FAMILIES
        for row in _index_rows(args, family)
    ]
    return sorted(rows, key=lambda row: (str(row["artifact_type"]), str(row["id"])))


def cmd_index_plans(args: argparse.Namespace) -> None:
    print(f"indexed {len(index_plans(args))} plan artifacts")


def cmd_write_plan(args: argparse.Namespace) -> None:
    if getattr(args, "filename", None):
        raise SystemExit("Plan filename override is not supported by the canonical family")
    if args.status not in PLAN_QUALIFICATION_STATUSES:
        raise SystemExit(f"Invalid plan qualification status: {args.status}")
    semantic = _semantic_yaml(
        Path(args.content_file), PLAN_STRUCTURAL_INPUT_FIELDS, "Root plan"
    )
    pid = args.id or _next_plan_id(args)
    source_spec_id = str(getattr(args, "source_spec_id", "") or "")
    if not source_spec_id:
        raise SystemExit("Root plan requires --source-spec-id")
    today = now_date()
    data = {
        **semantic,
        "artifact_type": "root-plan",
        "schema_version": 1,
        "id": pid,
        "goal": args.title,
        "purpose": args.purpose,
        "component": args.component,
        "version": args.version,
        "source_spec_id": source_spec_id,
        "status": args.status,
        "date_created": today,
        "last_updated": today,
    }
    bindings = {"source_spec": source_spec_id}
    _validate_candidate("root-plan", data, bindings)
    source = read_artifact(
        CATALOG_PATH, "specification", _plan_anchors(args),
        identity=source_spec_id, state="active",
    )
    if source["data"].get("status") != "verified":
        raise SystemExit("Root plan source specification must be active and verified")
    if _identity_collision(args, "root-plan", pid, bindings=bindings):
        raise SystemExit(f"Root plan canonical identity collision: {pid}")
    result = write_artifact(
        CATALOG_PATH, "root-plan", _plan_anchors(args), data, state="active",
        bindings=bindings,
    )
    print(rel(Path(str(result["path"])), args))


def cmd_list_plans(args: argparse.Namespace) -> None:
    rows = index_plans(args)
    for row in rows:
        if args.status and row.get("status") != args.status:
            continue
        if args.kind and row.get("type") != args.kind:
            continue
        print(json.dumps(row, ensure_ascii=False))


















def cmd_set_plan_status(args: argparse.Namespace) -> None:
    kind = getattr(args, "kind", None)
    if kind in {"phase", "task"}:
        raise SystemExit("stage5-required: phase/task execution-state mutation is not owned by Stage 4")
    if args.status not in PLAN_QUALIFICATION_STATUSES:
        raise SystemExit(f"Invalid plan qualification status: {args.status}")
    rows = [row for row in _index_rows(args, "root-plan") if row["id"] == args.id]
    if len(rows) != 1:
        raise SystemExit(f"Root plan not found at canonical location: {args.id}")
    row = rows[0]
    bindings = _family_bindings("root-plan", row)
    data = _active_artifact(args, "root-plan", args.id, bindings)
    if data["status"] == args.status:
        print(args.id)
        return
    if args.status not in PLAN_QUALIFICATION_TRANSITIONS[str(data["status"])]:
        raise SystemExit(
            f"Invalid plan qualification transition: {data['status']} -> {args.status}"
        )
    data["status"] = args.status
    data["last_updated"] = now_date()
    write_artifact(
        CATALOG_PATH, "root-plan", _plan_anchors(args), data, state="active",
        bindings=bindings,
    )
    print(args.id)


def cmd_archive_plan(args: argparse.Namespace) -> None:
    raise SystemExit(
        "unsupported: use finalize-reviewed-plan with current canonical artifacts"
    )
def _raise_finalization_partial(
    completed_operations: list[dict[str, str]],
    failed_operation: dict[str, str],
    error: BaseException,
) -> None:
    raise SystemExit(json.dumps({
        "status": "partial",
        "code": "WB_FINALIZATION_PARTIAL_EFFECT",
        "mutation_started": True,
        "completed_operations": completed_operations,
        "failed_operation": failed_operation,
        "error": str(error),
    }, ensure_ascii=False, sort_keys=True))


def _release_plan_bindings(
    control_root: Path,
    plan_id: str,
    bindings: list[dict[str, object]],
    completed_operations: list[dict[str, str]],
) -> dict[str, object]:
    """Release current task bindings whose ownership can truthfully terminate."""

    store = ManagedProvenanceStore(
        control_root / ".work-bundle/runtime/completion-provenance"
    )
    released: list[str] = []
    for binding in bindings:
        if binding.get("plan_id") != plan_id:
            continue
        ownership = binding.get("ownership")
        assert isinstance(ownership, dict)
        state = str(ownership.get("state") or "")
        if state == "released":
            released.append(str(binding.get("task_id") or ""))
            continue
        task_id = str(binding.get("task_id") or "unknown")
        binding_id = str(ownership["binding_id"])
        release_operation = {
            "operation": "binding-release",
            "task_id": task_id,
            "binding_id": binding_id,
        }
        try:
            updated_ownership = release_completion_binding(
                store,
                binding_id,
                owner=str(ownership["original_owner"]),
            ).to_dict()
        except (Exception, SystemExit) as error:
            _raise_finalization_partial(completed_operations, release_operation, error)
        completed_operations.append({
            "operation": "binding-provenance-release",
            "task_id": task_id,
            "binding_id": binding_id,
        })
        persist_operation = {
            "operation": "binding-file-persist",
            "task_id": task_id,
            "binding_id": binding_id,
        }
        try:
            _persist_binding({**binding, "ownership": updated_ownership}, control_root)
        except (Exception, SystemExit) as error:
            _raise_finalization_partial(completed_operations, persist_operation, error)
        completed_operations.append(persist_operation)
        released.append(task_id)
    return {"released": sorted(value for value in released if value)}


def cmd_write_phase(args: argparse.Namespace) -> None:
    if args.status != PLANNED_STATUS:
        raise SystemExit("Phase status must be planned; execution states require Stage 5")
    semantic = _semantic_yaml(
        Path(args.content_file), PHASE_STRUCTURAL_INPUT_FIELDS, "Phase"
    )
    today = now_date()
    data = {
        **semantic,
        "artifact_type": "phase", "schema_version": 1,
        "id": args.phase_id, "plan_id": args.plan_id, "name": args.title,
        "status": PLANNED_STATUS, "date_created": today, "last_updated": today,
    }
    bindings = {"plan": args.plan_id}
    _validate_candidate("phase", data, bindings)
    _active_root_plan(args, str(args.plan_id))
    if _identity_collision(args, "phase", args.phase_id, bindings=bindings):
        raise SystemExit(f"Phase canonical identity collision: {args.phase_id}")
    result = write_artifact(
        CATALOG_PATH, "phase", _plan_anchors(args), data, state="active",
        bindings=bindings,
    )
    print(rel(Path(str(result["path"])), args))


def cmd_write_task(args: argparse.Namespace) -> None:
    if args.status != PLANNED_STATUS:
        raise SystemExit("Task status must be planned; execution states require Stage 5")
    semantic = _semantic_yaml(
        Path(args.content_file), TASK_STRUCTURAL_INPUT_FIELDS, "Task"
    )
    source_obligation_records(semantic, label="Task")
    today = now_date()
    data = {
        **semantic,
        "artifact_type": "task", "schema_version": 2,
        "id": args.task_id, "plan_id": args.plan_id, "phase_id": args.phase_id,
        "name": args.title, "status": PLANNED_STATUS,
        "date_created": today, "last_updated": today,
    }
    bindings = {"plan": args.plan_id, "phase": args.phase_id}
    _validate_candidate("task", data, bindings)
    _active_root_plan(args, str(args.plan_id))
    try:
        read_artifact(
            CATALOG_PATH,
            "phase",
            _plan_anchors(args),
            identity=str(args.phase_id),
            state="active",
            bindings={"plan": str(args.plan_id)},
        )
    except (FileNotFoundError, SystemExit) as error:
        raise SystemExit(
            f"Task parent phase is not canonical for plan {args.plan_id}: {args.phase_id}"
        ) from error
    if _identity_collision(args, "task", args.task_id, bindings=bindings):
        raise SystemExit(f"Task canonical identity collision: {args.task_id}")
    result = write_artifact(
        CATALOG_PATH, "task", _plan_anchors(args), data, state="active",
        bindings=bindings,
    )
    print(rel(Path(str(result["path"])), args))


def cmd_finalize_reviewed_plan(args: argparse.Namespace) -> None:
    """Mechanically archive one exact accepted current plan and release bindings."""

    from artifact_store import transition_artifact
    from review_runtime import CURRENT_CATALOG

    anchors = _plan_anchors(args)
    review = read_artifact(
        CURRENT_CATALOG,
        "final-workflow-review",
        anchors,
        identity=str(args.final_review_id),
        state="active",
        bindings={"plan": str(args.plan_id)},
    )
    data = review["data"]
    if data.get("verdict") != "accept" or data.get("archive_ready") is not True:
        raise SystemExit("Final workflow review does not authorize archive readiness")
    knowledge = data.get("knowledge_return")
    if not isinstance(knowledge, dict) or knowledge.get("status") not in {"completed", "not-needed"}:
        raise SystemExit("Final workflow review knowledge return is not closed")

    plan_rows = [row for row in _index_rows(args, "root-plan") if row.get("id") == args.plan_id]
    if len(plan_rows) != 1:
        raise SystemExit("Finalization requires one canonical plan identity")
    plan_row = plan_rows[0]
    plan_bindings = _family_bindings("root-plan", plan_row)
    plan_record = read_artifact(
        CATALOG_PATH, "root-plan", anchors, identity=str(args.plan_id),
        state="active", bindings=plan_bindings,
    )
    plan_ref = data.get("plan_identity")
    if (
        not isinstance(plan_ref, dict)
        or plan_ref.get("id") != args.plan_id
        or plan_ref != canonical_plan_tree_identity(
            resolve_workspace_root(args), str(args.plan_id), state="active"
        )
        or data.get("specification_id") != plan_record["data"].get("source_spec_id")
    ):
        raise SystemExit("Final workflow review plan/specification identity is stale")

    task_rows = [row for row in _index_rows(args, "task") if row.get("plan_id") == args.plan_id]
    task_ids = {str(row["id"]) for row in task_rows}
    review_required_by_task: dict[str, bool] = {}
    for row in task_rows:
        task_id = str(row["id"])
        task_record = read_artifact(
            CATALOG_PATH,
            "task",
            anchors,
            identity=task_id,
            state="active",
            bindings=_family_bindings("task", row),
        )
        acceptance_review = task_record["data"].get("acceptance_review")
        required = acceptance_review.get("required") if isinstance(acceptance_review, dict) else None
        if type(required) is not bool:
            raise SystemExit(f"Finalization task acceptance-review contract is invalid: {task_id}")
        review_required_by_task[task_id] = required
    accepted_refs = data.get("accepted_results")
    if not isinstance(accepted_refs, list) or {str(ref.get("task_id")) for ref in accepted_refs if isinstance(ref, dict)} != task_ids:
        raise SystemExit("Final workflow review does not reference every planned task exactly once")
    if len(accepted_refs) != len(task_ids):
        raise SystemExit("Final workflow review accepted-result coverage is duplicated")
    coverage = data.get("coverage")
    if not isinstance(coverage, dict) or coverage != {"planned": len(task_ids), "accepted": len(task_ids), "missing": []}:
        raise SystemExit("Final workflow review coverage does not match canonical tasks")

    accepted_records: list[tuple[dict[str, object], dict[str, str]]] = []
    executor_records: list[tuple[dict[str, object], dict[str, str], str]] = []
    declared_review_refs = {
        (str(reference.get("id")), str(reference.get("sha256")))
        for reference in data.get("accepted_reviews", []) if isinstance(reference, dict)
    }
    expected_review_refs: set[tuple[str, str]] = set()
    for reference in accepted_refs:
        task_id = str(reference["task_id"])
        bindings = {"plan": str(args.plan_id), "task": task_id}
        record = read_artifact(
            CURRENT_CATALOG, "accepted-task-result", anchors,
            identity=str(reference["id"]), state="active", bindings=bindings,
        )
        if record["digest"] != reference.get("sha256") or record["data"].get("task_id") != reference["task_id"]:
            raise SystemExit("Final workflow review accepted-result reference is stale")
        accepted_data = record["data"]
        implementation_ref = accepted_data.get("implementation_review")
        if implementation_ref is None:
            if review_required_by_task[task_id]:
                raise SystemExit("Final workflow review omits a required implementation review")
        elif isinstance(implementation_ref, dict):
            implementation_identity = (
                str(implementation_ref.get("id")),
                str(implementation_ref.get("sha256")),
            )
            if implementation_identity not in declared_review_refs:
                raise SystemExit("Final workflow review implementation-review reference is invalid")
            expected_review_refs.add(implementation_identity)
        else:
            raise SystemExit("Final workflow review implementation-review reference is invalid")
        executor_ref = accepted_data.get("executor_result")
        executor_matches = []
        if isinstance(executor_ref, dict):
            for state in _plan_policy("executor-result")["lifecycle"]["states"]:
                try:
                    executor_matches.append(read_artifact(
                        CURRENT_CATALOG, "executor-result", anchors,
                        identity=str(executor_ref.get("id")), state=str(state), bindings=bindings,
                    ))
                except (FileNotFoundError, SystemExit):
                    continue
        if len(executor_matches) != 1 or executor_matches[0]["digest"] != executor_ref.get("sha256"):
            raise SystemExit("Final workflow review accepted-result executor reference is stale")
        executor_records.append((executor_matches[0], bindings, str(executor_matches[0]["state"])))
        accepted_records.append((record, bindings))

    if declared_review_refs != expected_review_refs:
        raise SystemExit("Final workflow review implementation-review coverage is not exact")

    review_records: list[dict[str, object]] = []
    for reference in data.get("accepted_reviews", []):
        record = read_artifact(
            CURRENT_CATALOG, "implementation-review", anchors,
            identity=str(reference["id"]), state="active", bindings={"plan": str(args.plan_id)},
        )
        if record["digest"] != reference.get("sha256") or record["data"].get("verdict") != "accept":
            raise SystemExit("Final workflow review implementation-review reference is stale")
        review_records.append(record)

    repository = data.get("repository_finalization")
    repositories = repository.get("repositories") if isinstance(repository, dict) else None
    if not isinstance(repositories, list) or not repositories:
        raise SystemExit("Final workflow review requires concrete repository baselines")
    for baseline in repositories:
        root = Path(str(baseline.get("root") or "")).expanduser().resolve()
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, check=False)
        if head.returncode or dirty.returncode or head.stdout.strip() != baseline.get("head") or dirty.stdout:
            raise SystemExit(f"Finalization repository baseline is not exact and clean: {baseline.get('repository_id')}")

    workspace_root = resolve_workspace_root(args)
    bindings = [binding for binding in _iter_task_bindings(workspace_root) if binding.get("plan_id") == args.plan_id]
    for binding in bindings:
        ownership = binding.get("ownership")
        try:
            validated_ownership = validate_ownership_shape(ownership) if isinstance(ownership, dict) else None
            if validated_ownership is not None and validated_ownership.get("state") != "released":
                validate_execution_binding_ownership(
                    workspace_root / ".work-bundle/runtime/completion-provenance",
                    validated_ownership,
                )
        except CompletionProvenanceError as error:
            raise SystemExit("Finalization task binding ownership is invalid") from error
        if validated_ownership is None or validated_ownership.get("state") not in {"active", "releasable", "released"}:
            raise SystemExit("Finalization task binding cannot be safely released")
        if validated_ownership["state"] in {"active", "releasable"} and (
            validated_ownership.get("current_owner") != validated_ownership.get("original_owner")
            or validated_ownership.get("repair_owner") is not None
            or validated_ownership.get("rereview_owner") is not None
            or (
                validated_ownership["state"] == "releasable"
                and validated_ownership.get("releasable") is not True
            )
        ):
            raise SystemExit("Finalization task binding cannot be safely released")

    # Check every archive destination before the first mutation.
    transitions: list[tuple[Path, str, str, dict[str, str]]] = []
    transition_states: dict[tuple[str, str], str] = {}
    for record, bindings_for_result, state in executor_records:
        identity = str(record["data"]["id"])
        transitions.append((CURRENT_CATALOG, "executor-result", identity, bindings_for_result))
        transition_states[("executor-result", identity)] = state
    for record, bindings_for_result in accepted_records:
        transitions.append((CURRENT_CATALOG, "accepted-task-result", str(record["data"]["id"]), bindings_for_result))
    for record in review_records:
        transitions.append((CURRENT_CATALOG, "implementation-review", str(record["data"]["id"]), {"plan": str(args.plan_id)}))
    for row in task_rows:
        transitions.append((CATALOG_PATH, "task", str(row["id"]), _family_bindings("task", row)))
    phase_rows = [row for row in _index_rows(args, "phase") if row.get("plan_id") == args.plan_id]
    for row in phase_rows:
        transitions.append((CATALOG_PATH, "phase", str(row["id"]), _family_bindings("phase", row)))
    transitions.append((CATALOG_PATH, "root-plan", str(args.plan_id), plan_bindings))
    transitions.append((CURRENT_CATALOG, "final-workflow-review", str(args.final_review_id), {"plan": str(args.plan_id)}))
    seen_transitions: set[tuple[str, str]] = set()
    for catalog, family, identity, bindings_for_item in transitions:
        transition_key = (family, identity)
        if transition_key in seen_transitions:
            raise SystemExit(f"Finalization contains a duplicate transition: {family}/{identity}")
        seen_transitions.add(transition_key)
        current_state = transition_states.get(transition_key, "active")
        policy = family_policy(load_catalog(catalog), family)
        if "archived" not in policy["lifecycle"]["transitions"].get(current_state, []):
            raise SystemExit(
                f"Finalization transition is not permitted: {family}/{identity} {current_state}->archived"
            )
        source = canonical_artifact_path(
            policy,
            anchors,
            identity=identity,
            state=current_state,
            bindings=bindings_for_item,
        )
        if not source.is_file() or source.is_symlink():
            raise SystemExit(f"Finalization archive source is unavailable: {source}")
        try:
            read_artifact(
                catalog,
                family,
                anchors,
                identity=identity,
                state=current_state,
                bindings=bindings_for_item,
            )
        except (FileNotFoundError, SystemExit, ValueError) as error:
            raise SystemExit(
                f"Finalization archive source is invalid: {family}/{identity}"
            ) from error
        destination = canonical_artifact_path(
            policy, anchors,
            identity=identity, state="archived", bindings=bindings_for_item,
        )
        if destination.exists():
            raise SystemExit(f"Finalization archive destination already exists: {destination}")

    completed_operations: list[dict[str, str]] = []
    released = _release_plan_bindings(
        workspace_root,
        str(args.plan_id),
        bindings,
        completed_operations,
    )
    results = []
    for catalog, family, identity, bindings_for_item in transitions:
        operation = {
            "operation": "artifact-transition",
            "family": family,
            "identity": identity,
        }
        try:
            results.append(transition_artifact(
                catalog, family, anchors, identity=identity,
                current_state=transition_states.get((family, identity), "active"),
                target_state="archived", bindings=bindings_for_item,
            ))
        except (Exception, SystemExit) as error:
            _raise_finalization_partial(completed_operations, operation, error)
        completed_operations.append(operation)
    for catalog, family, _identity, _bindings_for_item in transitions:
        operation = {
            "operation": "index-rebuild",
            "family": family,
            "identity": _identity,
        }
        try:
            rebuild_index(catalog, family, anchors)
        except (Exception, SystemExit) as error:
            _raise_finalization_partial(completed_operations, operation, error)
        completed_operations.append(operation)
    result = {
        "plan_id": str(args.plan_id), "final_review_id": str(args.final_review_id),
        "archived": len(results), "released_tasks": released["released"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
