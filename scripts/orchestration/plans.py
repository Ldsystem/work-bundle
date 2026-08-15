from core import *
from execution_context import (
    cmd_validate_executor_result,
    evaluate_knowledge_closure_state,
    read_structured_artifact,
    unique_explicit_handoff_plan_id,
    validate_executor_result_for_task,
    _compile_task_brief,
)
from specs import load_index, replace_front_matter_value


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
    )
    try:
        _, brief_document = _compile_task_brief(compile_args)
        brief = brief_document["task_brief"]
        validate_executor_result_for_task(handoff, brief)
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
    recorded: dict[str, set[str]] = {}
    for handoff, _brief in validated:
        validation = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else {}
        raw_commands = validation.get("commands")
        items = raw_commands if isinstance(raw_commands, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            command = str(item.get("command") or "").strip()
            if command:
                recorded.setdefault(command, set()).add(str(item.get("result") or ""))
    for command in commands:
        results = recorded.get(command, set())
        if results == {"passed"}:
            continue
        if not results:
            detail = "missing"
        elif len(results) > 1:
            detail = "contradictory"
        else:
            detail = next(iter(results))
        raise SystemExit(f"acceptance-blocked: declared plan-level acceptance {command} is {detail}")


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
        )
    )


def cmd_set_plan_status(args: argparse.Namespace) -> None:
    if args.status not in PLAN_STATUSES:
        raise SystemExit(f"Invalid plan status: {args.status}")
    rows = index_plans(args)
    matches = [row for row in rows if row.get("id") == args.id and (not args.kind or row.get("type") == args.kind)]
    if not matches:
        raise SystemExit(f"Plan artifact not found: {args.id}")
    if len(matches) > 1:
        raise SystemExit(f"Multiple plan artifacts match {args.id}; pass --kind plan|phase|task")
    row = matches[0]
    path = artifact_path_from_row(row, args)
    if args.status == "Completed" and row.get("type") == "task":
        _assert_completed_task_handoff(args, path)
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
    validated = _validated_plan_task_handoffs(args, args.id)
    _assert_archive_knowledge_gate(args, args.id, root_path, validated)
    _assert_archive_plan_acceptance(args, args.id, root_path, validated)
    if is_relative_to(root_path, active_root):
        replace_front_matter_value(root_path, "status", "Completed")
        moved.append(move_to_archive(root_path, active_root, archived_root))

    active_plan_dir = active_root / args.id
    if active_plan_dir.exists():
        archived_plan_dir = archived_root / args.id
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
