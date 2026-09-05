import hashlib
import subprocess
from datetime import datetime, timezone

from core import *
from core import _member_roots
from execution_context import (
    cmd_validate_executor_result,
    evaluate_knowledge_closure_state,
    read_structured_artifact,
    unique_explicit_handoff_plan_id,
    validate_executor_result_for_task,
    _compile_task_brief,
    _observation_kwargs,
    _parse_scalar,
    _execution_workspace_module,
    _persist_binding,
    load_task_execution_binding,
)
from completion_provenance import ManagedProvenanceStore, release_completion_binding
from handoffs import _read_compact_yaml_metadata
from repository_preflight import capture_repository_evidence, task_caused_paths
from specs import load_index, replace_front_matter_value
from review_runtime import require_plan_reviews


def _plan_knowledge_field(body: str, label: str) -> str | None:
    section = re.search(
        r"^##\s+2\.1\s+Knowledge Base Update Carry Forward\s*$([\s\S]*?)(?=^##\s|\Z)",
        body,
        re.MULTILINE,
    )
    if not section:
        return None
    match = re.search(rf"^-\s+\*\*{re.escape(label)}\*\*:\s*([^\s]+)\s*$", section.group(1), re.MULTILINE)
    return match.group(1) if match else None


def _assert_archive_knowledge_gate(
    args: argparse.Namespace,
    plan_id: str,
    root_path: Path,
    validated: list[tuple[dict[str, object], dict[str, object]]],
) -> None:
    _, body = read_front_matter(root_path)
    upstream = _plan_knowledge_field(body, "Disposition")
    if upstream is None:
        raise SystemExit("knowledge-blocked: plan has no Knowledge Base Update disposition")
    closure_return = _plan_knowledge_field(body, "Closure return") or "missing"
    handoffs = [handoff for handoff, _brief in validated]
    review_required_by_task = {
        str(brief.get("task_id") or ""): brief.get("review_required") is True for _handoff, brief in validated
    }
    gate = evaluate_knowledge_closure_state(
        upstream_disposition=upstream,
        accepted_task_handoffs=handoffs,
        closure_return=closure_return,
        review_required_by_task=review_required_by_task,
    )
    if gate["archive_blocked"]:
        triggers = ", ".join(f"{item['task']}:{item['action']}" for item in gate["triggers"])
        detail = triggers or str(gate["disposition"])
        raise SystemExit(f"knowledge-blocked: archive requires resolved durable closure ({detail})")


def _plan_executor_handoffs(args: argparse.Namespace, plan_id: str) -> list[dict[str, object]]:
    handoffs: list[dict[str, object]] = []
    handoff_root = orchestration_root(args) / "handoff" / "executor"
    for path in sorted(handoff_root.glob("*/*")):
        if not path.is_file() or path.suffix not in {".yaml", ".yml"}:
            continue
        compact = _read_compact_yaml_metadata(path)
        if isinstance(compact.get("related"), str):
            related = _parse_scalar(str(compact["related"]))
            if isinstance(related, dict):
                compact["related"] = related
        compact_plan_id = unique_explicit_handoff_plan_id(compact)
        if compact_plan_id is not None and compact_plan_id != plan_id:
            continue
        handoff = read_structured_artifact(path)
        if unique_explicit_handoff_plan_id(handoff) != plan_id:
            continue
        handoffs.append(handoff)
    return handoffs


def _find_plan_task_path(args: argparse.Namespace, plan_id: str, task_id: str) -> Path | None:
    matches = [
        row
        for row in index_plans(args)
        if row.get("type") == "task" and row.get("id") == task_id and row.get("plan_id") == plan_id
    ]
    if len(matches) != 1:
        return None
    return artifact_path_from_row(matches[0], args)


def _try_validate_task_handoff(
    args: argparse.Namespace, plan_id: str, handoff: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]] | None:
    related = handoff.get("related") if isinstance(handoff.get("related"), dict) else {}
    task_id = related.get("task")
    if not task_id:
        return None
    task_path = _find_plan_task_path(args, plan_id, str(task_id))
    if task_path is None:
        return None
    compile_args = argparse.Namespace(
        project_root=getattr(args, "project_root", None),
        workspace_root=getattr(args, "workspace_root", None),
        task=str(task_path),
        handoff=None,
        base=None,
        head=None,
        **_observation_kwargs(args),
    )
    try:
        _, brief_document = _compile_task_brief(compile_args)
        brief = brief_document["task_brief"]
        capability = brief.get("evidence_capability") if isinstance(brief.get("evidence_capability"), dict) else {}
        validate_executor_result_for_task(
            handoff,
            brief,
            observe=capability.get("result") == "mapped",
            **_observation_kwargs(args),
        )
    except SystemExit:
        return None
    return handoff, brief


def _validated_plan_task_handoffs(
    args: argparse.Namespace, plan_id: str
) -> list[tuple[dict[str, object], dict[str, object]]]:
    validated: list[tuple[dict[str, object], dict[str, object]]] = []
    for handoff in _plan_executor_handoffs(args, plan_id):
        pair = _try_validate_task_handoff(args, plan_id, handoff)
        if pair is not None:
            validated.append(pair)
    return validated


def _plan_section_table(body: str, name: str) -> list[list[str]]:
    section = re.search(
        rf"^##\s+(?:\d+(?:\.\d+)*\.?\s+)?{re.escape(name)}\s*$([\s\S]*?)(?=^##\s|\Z)",
        body,
        re.MULTILINE,
    )
    if not section:
        return []
    rows: list[list[str]] = []
    for line in section.group(1).splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows[1:] if rows else []


def _declared_integration_commands(body: str) -> list[str]:
    commands: list[str] = []
    for cells in _plan_section_table(body, "Tests"):
        if len(cells) < 6:
            continue
        test_type = cells[1].lower()
        if "integration" not in test_type or "unit|integration" in test_type:
            continue
        command = cells[5].strip().strip("`")
        if command and command not in {"-", "[command if applicable]"}:
            commands.append(command)
    return commands


_MATERIAL_CHANGE_ACTIONS = {"created", "modified", "deleted"}
_MATERIAL_RESULT_STATES = {"completed", "partial"}


def _git_tree_id(root: Path, spec: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", f"{spec}^{{tree}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _handoff_recorded_identities(handoff: dict[str, object]) -> list[str]:
    identities: list[str] = []
    review = handoff.get("acceptance_review") if isinstance(handoff.get("acceptance_review"), dict) else {}
    reviewed_head = str(review.get("reviewed_head") or "").strip()
    if reviewed_head:
        identities.append(reviewed_head)
    repositories = handoff.get("repository")
    if isinstance(repositories, dict):
        repositories = [repositories]
    if isinstance(repositories, list):
        for repository in repositories:
            if not isinstance(repository, dict):
                continue
            metadata = repository.get("metadata") if isinstance(repository.get("metadata"), dict) else {}
            actual_commit = str(metadata.get("actual_commit") or "").strip()
            if actual_commit:
                identities.append(actual_commit)
    return identities


def _verified_handoff_tree(root: Path, handoff: dict[str, object]) -> str | None:
    repositories = handoff.get("repository") if isinstance(handoff.get("repository"), list) else []
    for repository in repositories:
        if not isinstance(repository, dict):
            continue
        recorded_root = str(repository.get("root") or "").strip()
        metadata = repository.get("metadata") if isinstance(repository.get("metadata"), dict) else {}
        identity = str(metadata.get("actual_commit") or "").strip()
        if recorded_root and identity:
            tree = _git_tree_id(Path(recorded_root).expanduser().resolve(), identity)
            if tree:
                return tree
    for identity in _handoff_recorded_identities(handoff):
        tree = _git_tree_id(root, identity)
        if tree:
            return tree
    return None


def _plan_task_order(args: argparse.Namespace, plan_id: str) -> dict[str, int]:
    order: dict[str, int] = {}
    for row in index_plans(args):
        if row.get("type") != "task" or row.get("plan_id") != plan_id:
            continue
        front_matter, _body = read_front_matter(artifact_path_from_row(row, args))
        task_id = str(front_matter.get("id") or row.get("id") or "")
        value = front_matter.get("order")
        rank: int | None = None
        if isinstance(value, int) and not isinstance(value, bool):
            rank = value
        elif isinstance(value, str) and re.fullmatch(r"[1-9]\d*", value.strip()):
            rank = int(value)
        if task_id and rank is not None:
            if rank in order.values():
                raise SystemExit("acceptance-blocked: final plan task order is ambiguous")
            order[task_id] = rank
    return order


def _material_repository_root(
    args: argparse.Namespace,
    plan_id: str,
    validated: list[tuple[dict[str, object], dict[str, object]]],
    commands: list[str],
) -> Path:
    entries: list[tuple[Path, str]] = []
    material = [pair for pair in validated if _handoff_has_material_changes(*pair)]
    if not material:
        return project_root(args)
    for handoff, _brief in material:
        handoff_has_provenance = False
        repositories = handoff.get("repository") if isinstance(handoff.get("repository"), list) else []
        for repository in repositories:
            if not isinstance(repository, dict):
                continue
            recorded = str(repository.get("root") or "").strip()
            metadata = repository.get("metadata") if isinstance(repository.get("metadata"), dict) else {}
            identity = str(metadata.get("actual_commit") or "").strip()
            if recorded and identity:
                entries.append((Path(recorded).expanduser().resolve(), identity))
                handoff_has_provenance = True
        if not handoff_has_provenance:
            try:
                fallback = _resolve_final_plan_workspace(args)
            except SystemExit as error:
                raise SystemExit(
                    "acceptance-blocked: material handoff repository provenance is unavailable"
                ) from error
            entries.append((fallback, "HEAD"))
    roots = {root for root, _identity in entries}
    if len(roots) == 1:
        return next(iter(roots))
    task_order = _plan_task_order(args, plan_id)
    material_ranks: list[int] = []
    for handoff, brief in validated:
        if not _handoff_has_material_changes(handoff, brief):
            continue
        task_id = str(brief.get("task_id") or "")
        if task_id not in task_order:
            raise SystemExit("acceptance-blocked: final plan task order is unavailable")
        material_ranks.append(task_order[task_id])
    terminal_material_rank = max(material_ranks) if material_ranks else -1
    acceptance_entries: list[tuple[Path, str]] = []
    for handoff, brief in validated:
        if not any(_handoff_command_result(handoff, command) == "passed" for command in commands):
            continue
        task_id = str(brief.get("task_id") or "")
        rank = task_order.get(task_id)
        if rank is None or rank < terminal_material_rank:
            continue
        repositories = handoff.get("repository") if isinstance(handoff.get("repository"), list) else []
        for repository in repositories:
            if not isinstance(repository, dict):
                continue
            recorded = str(repository.get("root") or "").strip()
            metadata = repository.get("metadata") if isinstance(repository.get("metadata"), dict) else {}
            identity = str(metadata.get("actual_commit") or "").strip()
            if recorded and identity:
                acceptance_entries.append((Path(recorded).expanduser().resolve(), identity))
    fresh_acceptance_roots: set[Path] = set()
    for root, identity in acceptance_entries:
        head_tree = _git_tree_id(root, "HEAD")
        recorded_tree = _git_tree_id(root, identity)
        if head_tree is not None and recorded_tree is not None and head_tree == recorded_tree:
            fresh_acceptance_roots.add(root)
    if len(fresh_acceptance_roots) == 1:
        return next(iter(fresh_acceptance_roots))
    raise SystemExit("acceptance-blocked: final plan repository is ambiguous")


def _acceptance_result_detail(results: set[str]) -> str:
    if not results:
        return "missing"
    if len(results) > 1:
        return "contradictory"
    return next(iter(results))


def _handoff_command_result(handoff: dict[str, object], command: str) -> str | None:
    validation = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else {}
    items = validation.get("commands") if isinstance(validation.get("commands"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("command") or "").strip() == command:
            return str(item.get("result") or "")
    return None


def _handoff_has_material_changes(handoff: dict[str, object], brief: dict[str, object]) -> bool:
    changes = handoff.get("changes") if isinstance(handoff.get("changes"), dict) else {}
    items = changes.get("files") if isinstance(changes.get("files"), list) else []
    for item in items:
        if isinstance(item, dict) and str(item.get("action") or "") in _MATERIAL_CHANGE_ACTIONS:
            return True
    result = handoff.get("result") if isinstance(handoff.get("result"), dict) else {}
    if str(result.get("state") or "") not in _MATERIAL_RESULT_STATES:
        return False
    files = brief.get("files") if isinstance(brief.get("files"), dict) else {}
    write = files.get("write")
    return bool(write) if isinstance(write, list) else False


def _resolve_final_plan_workspace(args: argparse.Namespace) -> Path:
    workspace = resolve_workspace_root(args)
    try:
        members = _member_roots(workspace)
    except OSError:
        members = []
    if len(members) > 1:
        raise SystemExit("acceptance-blocked: final plan workspace is ambiguous")
    target = members[0] if members else workspace
    if not target.is_dir():
        raise SystemExit("acceptance-blocked: final plan workspace is missing")
    return target


def _observe_archive_command(command: str, workspace: Path) -> str:
    completed = subprocess.run(
        command,
        shell=True,
        cwd=str(workspace),
        capture_output=True,
        text=True,
        check=False,
    )
    return "passed" if completed.returncode == 0 else "failed"


def _assert_archive_command_state_neutral(command: str, workspace: Path) -> None:
    try:
        pre = capture_repository_evidence(workspace)
    except RuntimeError as error:
        raise SystemExit(f"acceptance-blocked: {error}") from error
    result = _observe_archive_command(command, workspace)
    if result != "passed":
        raise SystemExit(f"acceptance-blocked: declared plan-level acceptance {command} is {result}")
    try:
        post = capture_repository_evidence(workspace)
    except RuntimeError as error:
        raise SystemExit(f"acceptance-blocked: {error}") from error
    caused = task_caused_paths(pre, post, workspace)
    if caused or pre != post:
        raise SystemExit(
            "acceptance-blocked: declared plan-level acceptance mutated Git-observable state"
        )


def _assert_archive_plan_acceptance(
    args: argparse.Namespace,
    plan_id: str,
    root_path: Path,
    validated: list[tuple[dict[str, object], dict[str, object]]],
) -> None:
    _, body = read_front_matter(root_path)
    commands = _declared_integration_commands(body)
    if not commands:
        return
    git_root = _material_repository_root(args, plan_id, validated, commands)
    terminal_tree = _git_tree_id(git_root, "HEAD")
    material = [pair for pair in validated if _handoff_has_material_changes(*pair)]
    for command in commands:
        terminal_results: set[str] = set()
        other_results: set[str] = set()
        for handoff, _brief in validated:
            result = _handoff_command_result(handoff, command)
            if result is None:
                continue
            tree = _verified_handoff_tree(git_root, handoff)
            if terminal_tree and tree == terminal_tree:
                terminal_results.add(result)
            else:
                other_results.add(result)
        judged = terminal_results or other_results
        if terminal_results:
            if terminal_results == {"passed"}:
                continue
            raise SystemExit(
                f"acceptance-blocked: declared plan-level acceptance {command} is {_acceptance_result_detail(terminal_results)}"
            )
        if judged == {"passed"}:
            if len(material) <= 1:
                continue
            raise SystemExit(f"acceptance-blocked: declared plan-level acceptance {command} is stale")
        raise SystemExit(
            f"acceptance-blocked: declared plan-level acceptance {command} is {_acceptance_result_detail(judged)}"
        )
    workspace = git_root if material else _resolve_final_plan_workspace(args)
    for command in commands:
        _assert_archive_command_state_neutral(command, workspace)


def index_plans(args: argparse.Namespace) -> list[dict[str, object]]:
    root = orchestration_root(args) / "plan"
    rows = []
    for path in sorted(root.glob("active/*.md")) + sorted(root.glob("archived/*.md")):
        fm, _ = read_front_matter(path)
        if not fm:
            continue
        rows.append(
            {
                "type": "plan",
                "id": fm.get("id", path.stem),
                "title": fm.get("goal", fm.get("title", path.stem)),
                "status": fm.get("status", "Planned"),
                "path": rel(path, args),
                "purpose": fm.get("purpose", ""),
                "component": fm.get("component", ""),
                "created_at": fm.get("date_created", ""),
                "updated_at": fm.get("last_updated", ""),
            }
        )
    for path in sorted(root.glob("active/*/phase-*.md")) + sorted(root.glob("archived/*/phase-*.md")):
        fm, _ = read_front_matter(path)
        if not fm:
            continue
        rows.append(
            {
                "type": "phase",
                "id": fm.get("id", path.stem),
                "plan_id": fm.get("plan_id", path.parent.name),
                "title": fm.get("name", fm.get("title", path.stem)),
                "status": fm.get("status", "Planned"),
                "path": rel(path, args),
                "created_at": fm.get("date_created", ""),
                "updated_at": fm.get("last_updated", ""),
            }
        )
    for path in sorted(root.glob("active/*/phase-*/*.md")) + sorted(root.glob("archived/*/phase-*/*.md")):
        fm, _ = read_front_matter(path)
        if not fm:
            continue
        rows.append(
            {
                "type": "task",
                "id": fm.get("id", path.stem),
                "plan_id": fm.get("plan_id", path.parents[1].name),
                "phase_id": fm.get("phase_id", path.parent.name),
                "title": fm.get("name", fm.get("title", path.stem)),
                "status": fm.get("status", "Planned"),
                "path": rel(path, args),
                "task_type": fm.get("task_type", ""),
                "created_at": fm.get("date_created", ""),
                "updated_at": fm.get("last_updated", ""),
            }
        )
    (root / "index.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
    return rows


def cmd_index_plans(args: argparse.Namespace) -> None:
    print(f"indexed {len(index_plans(args))} plan artifacts")


def cmd_write_plan(args: argparse.Namespace) -> None:
    init_dirs(args)
    if args.status not in PLAN_STATUSES:
        raise SystemExit(f"Invalid plan status: {args.status}")
    pid = args.id or sequence_id(orchestration_root(args) / "plan" / "active", "plan")
    filename = args.filename or f"{args.purpose}-{slugify(args.component)}-{args.version}.md"
    content = Path(args.content_file).read_text(encoding="utf-8")
    content = ensure_front_matter(content, {"id": pid, "goal": args.title, "purpose": args.purpose, "component": args.component, "version": args.version, "date_created": now_date(), "last_updated": now_date(), "owner": "agent", "status": args.status})
    target = orchestration_root(args) / "plan" / "active" / filename
    from execution_context import parse_yaml_subset
    effective_status = parse_yaml_subset(content.split("---", 2)[1]).get("status")
    if effective_status in {"In progress", "Completed"} or args.status in {"In progress", "Completed"}:
        require_plan_reviews(project_root(args), target, content=content,
                             source_root=_resolve_final_plan_workspace(args) if "Completed" in {effective_status, args.status} else None)
    write_text_safely(target, content, args)
    index_plans(args)
    print(rel(target, args))


def cmd_list_plans(args: argparse.Namespace) -> None:
    rows = index_plans(args)
    for row in rows:
        if args.status and row.get("status") != args.status:
            continue
        if args.kind and row.get("type") != args.kind:
            continue
        print(json.dumps(row, ensure_ascii=False))


def _assert_completed_task_handoff(args: argparse.Namespace, task_path: Path) -> None:
    handoff = getattr(args, "handoff", None)
    if not handoff:
        raise SystemExit("set-plan-status Completed for a task requires --handoff")
    cmd_validate_executor_result(
        argparse.Namespace(
            project_root=getattr(args, "project_root", None),
            workspace_root=getattr(args, "workspace_root", None),
            task=str(task_path),
            handoff=str(handoff),
            base=None,
            head=None,
            **_observation_kwargs(args),
        )
    )


def _release_completed_task_binding(args: argparse.Namespace, row: dict[str, object]) -> dict[str, object]:
    """Release and persist API-006 ownership after executor-result validation succeeds."""

    control_root = resolve_workspace_root(args)
    plan_id = str(row["plan_id"])
    task_id = str(row["id"])
    binding = load_task_execution_binding(control_root, plan_id, task_id)
    handoff = Path(str(getattr(args, "handoff", "")))
    artifact_digest = hashlib.sha256(handoff.read_bytes()).hexdigest() if handoff.is_file() else None
    event = {
        "event_id": "event-template",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "process_id": "process-plan-status",
        "stage": "task-completion",
        "attempt_id": str(binding["execution_id"]),
        "event_type": "binding_released",
        "enforcement_mode": "native",
        "join_ids": {
            "specification_id": None,
            "plan_id": plan_id,
            "phase_id": str(row.get("phase_id") or "") or None,
            "task_id": task_id,
            "review_id": None,
            "evaluation_id": None,
        },
        "clocks": {"wall_ms": 0, "active_ms": 0, "billed_ms": None},
        "finding_class": None,
        "return_reason": "validated completion",
        "owner": task_id,
        "identity": {"product_tree": None, "artifact_digest": artifact_digest, "mutation_epoch": 0},
        "privacy": "operational_metadata_only",
    }
    store = ManagedProvenanceStore(control_root / ".work-bundle/runtime/completion-provenance")
    released = release_completion_binding(
        store,
        str(binding["ownership"]["binding_id"]),
        owner=task_id,
        stage_event_workspace=control_root,
        stage_event=event,
    ).to_dict()
    updated = {**binding, "ownership": released}
    _persist_binding(updated, control_root)
    if released["target_kind"] == "isolated_worktree":
        _execution_workspace_module().retain_binding_owner(
            Path(str(binding["runtime_root"])),
            str(binding["workspace_id"]),
            str(binding["execution_id"]),
            str(binding["repository_id"]),
            ownership=released,
        )
    return released


def cmd_set_plan_status(args: argparse.Namespace) -> None:
    if args.status not in PLAN_STATUSES:
        raise SystemExit(f"Invalid plan status: {args.status}")
    rows = index_plans(args)
    kind = getattr(args, "kind", None)
    plan_id = getattr(args, "plan_id", None)
    matches = [
        row
        for row in rows
        if row.get("id") == args.id
        and (not kind or row.get("type") == kind)
        and (not plan_id or row.get("plan_id") == plan_id)
    ]
    if not matches:
        raise SystemExit(f"Plan artifact not found: {args.id}")
    if len(matches) > 1:
        selectors = []
        if not kind:
            selectors.append("--kind plan|phase|task")
        if not plan_id:
            selectors.append("--plan-id PLAN_ID")
        guidance = f"; pass {' and '.join(selectors)}" if selectors else "; supplied selectors remain ambiguous"
        raise SystemExit(f"Multiple plan artifacts match {args.id}{guidance}")
    row = matches[0]
    path = artifact_path_from_row(row, args)
    if row.get("type") == "plan" and args.status in {"In progress", "Completed"}:
        require_plan_reviews(project_root(args), path,
                             source_root=_resolve_final_plan_workspace(args) if args.status == "Completed" else None)
    if args.status == "Completed" and row.get("type") == "task":
        _assert_completed_task_handoff(args, path)
        _release_completed_task_binding(args, row)
    replace_front_matter_value(path, "status", args.status)
    if args.status == "Deprecated":
        active_root = orchestration_root(args) / "plan" / "active"
        archived_root = orchestration_root(args) / "plan" / "archived"
        if is_relative_to(path, active_root):
            move_to_archive(path, active_root, archived_root)
    index_plans(args)
    print(args.id)


def cmd_archive_plan(args: argparse.Namespace) -> None:
    rows = index_plans(args)
    root_match = next((row for row in rows if row.get("type") == "plan" and row.get("id") == args.id), None)
    if not root_match:
        raise SystemExit(f"Plan artifact not found: {args.id}")

    active_root = orchestration_root(args) / "plan" / "active"
    archived_root = orchestration_root(args) / "plan" / "archived"
    moved = []

    root_path = artifact_path_from_row(root_match, args)
    require_plan_reviews(project_root(args), root_path, source_root=_resolve_final_plan_workspace(args))
    validated = _validated_plan_task_handoffs(args, args.id)
    _assert_archive_knowledge_gate(args, args.id, root_path, validated)
    _assert_archive_plan_acceptance(args, args.id, root_path, validated)
    require_plan_reviews(project_root(args), root_path, source_root=_resolve_final_plan_workspace(args))
    if is_relative_to(root_path, active_root):
        replace_front_matter_value(root_path, "status", "Completed")
        moved.append(move_to_archive(root_path, active_root, archived_root))

    sibling_plan_dir = root_path.with_suffix("")
    indexed_active_dirs = {
        active_root / artifact_path_from_row(row, args).relative_to(active_root).parts[0]
        for row in rows
        if row.get("type") == "task"
        and row.get("plan_id") == args.id
        and is_relative_to(artifact_path_from_row(row, args), active_root)
    }
    if sibling_plan_dir.is_dir() and is_relative_to(sibling_plan_dir, active_root):
        active_plan_dir = sibling_plan_dir
    elif len(indexed_active_dirs) == 1:
        active_plan_dir = next(iter(indexed_active_dirs))
    else:
        active_plan_dir = active_root / args.id
    if active_plan_dir.exists():
        archived_plan_dir = archived_root / active_plan_dir.name
        if archived_plan_dir.exists():
            raise SystemExit(f"Archived plan directory already exists: {archived_plan_dir}")
        archived_plan_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(active_plan_dir), str(archived_plan_dir))
        moved.append(archived_plan_dir)

    if not moved:
        raise SystemExit(f"Plan is not active or has no active files: {args.id}")

    index_plans(args)
    for path in moved:
        print(rel(path, args))


def cmd_write_phase(args: argparse.Namespace) -> None:
    content = Path(args.content_file).read_text(encoding="utf-8")
    content = ensure_front_matter(content, {"id": args.phase_id, "plan_id": args.plan_id, "name": args.title, "status": args.status, "date_created": now_date(), "last_updated": now_date()})
    target = orchestration_root(args) / "plan" / "active" / args.plan_id / f"{args.phase_id}-{slugify(args.title)}.md"
    write_text_safely(target, content, args)
    index_plans(args)
    print(rel(target, args))


def cmd_write_task(args: argparse.Namespace) -> None:
    content = Path(args.content_file).read_text(encoding="utf-8")
    content = ensure_front_matter(content, {"id": args.task_id, "phase_id": args.phase_id, "plan_id": args.plan_id, "name": args.title, "status": args.status, "date_created": now_date(), "last_updated": now_date()})
    plan_dir = orchestration_root(args) / "plan" / "active" / args.plan_id
    phase_dirs = sorted(plan_dir.glob(f"{args.phase_id}-*"))
    phase_dir = next((path for path in phase_dirs if path.is_dir()), plan_dir / f"{args.phase_id}-{slugify(args.phase_id)}")
    target = phase_dir / f"{args.task_id}-{slugify(args.title)}.md"
    write_text_safely(target, content, args)
    index_plans(args)
    print(rel(target, args))
