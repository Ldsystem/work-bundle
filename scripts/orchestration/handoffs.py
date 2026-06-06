from core import *
from specs import replace_front_matter_value

def index_handoffs(args: argparse.Namespace) -> list[dict[str, object]]:
    root = orchestration_root(args) / "handoff"
    rows = []
    for path in sorted(root.glob("*/*/*.md")):
        fm, _ = read_front_matter(path)
        if not fm:
            continue
        rows.append({"id": fm.get("id", path.stem), "type": fm.get("type", ""), "status": fm.get("status", "active"), "path": rel(path, args), "project": fm.get("project", ""), "created_at": fm.get("created_at", ""), "updated_at": fm.get("updated_at", ""), "related_spec": fm.get("related_spec", None), "related_plan": fm.get("related_plan", None), "related_phase": fm.get("related_phase", None), "related_task": fm.get("related_task", None)})
    (root / "index.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
    return rows


def cmd_write_handoff(args: argparse.Namespace) -> None:
    init_dirs(args)
    if args.type not in HANDOFF_TYPES:
        raise SystemExit(f"Invalid handoff type: {args.type}")
    if args.status not in HANDOFF_STATUSES:
        raise SystemExit(f"Invalid handoff status: {args.status}")
    hprefix = "handoff-orch" if args.type == "orchestration" else "handoff-exec"
    hid = args.id or sequence_id(orchestration_root(args) / "handoff", hprefix)
    folder = "orchestration" if args.type == "orchestration" else "executor"
    content = Path(args.content_file).read_text(encoding="utf-8")
    content = ensure_front_matter(content, {"id": hid, "type": args.type, "title": args.title, "status": args.status, "project": project_root(args).name, "created_at": now_date(), "updated_at": now_date(), "related_spec": args.related_spec or "null", "related_plan": args.related_plan or "null", "related_phase": args.related_phase or "null", "related_task": args.related_task or "null"})
    target_status_dir = "archived" if args.status == "archived" else "active"
    target = orchestration_root(args) / "handoff" / folder / target_status_dir / f"{hid}-{slugify(args.title)}.md"
    write_text_safely(target, content, args)
    index_handoffs(args)
    print(rel(target, args))


def cmd_index_handoffs(args: argparse.Namespace) -> None:
    print(f"indexed {len(index_handoffs(args))} handoffs")


def cmd_list_handoffs(args: argparse.Namespace) -> None:
    rows = index_handoffs(args)
    for row in rows:
        if args.status and row.get("status") != args.status:
            continue
        if args.type and row.get("type") != args.type:
            continue
        print(json.dumps(row, ensure_ascii=False))


def cmd_set_handoff_status(args: argparse.Namespace) -> None:
    if args.status not in HANDOFF_STATUSES:
        raise SystemExit(f"Invalid handoff status: {args.status}")
    rows = index_handoffs(args)
    match = next((row for row in rows if row.get("id") == args.id), None)
    if not match:
        raise SystemExit(f"Handoff not found: {args.id}")
    path = artifact_path_from_row(match, args)
    replace_front_matter_value(path, "status", args.status)
    if args.status == "archived":
        folder = "orchestration" if match.get("type") == "orchestration" else "executor"
        active_root = orchestration_root(args) / "handoff" / folder / "active"
        archived_root = orchestration_root(args) / "handoff" / folder / "archived"
        if is_relative_to(path, active_root):
            move_to_archive(path, active_root, archived_root)
    index_handoffs(args)
    print(args.id)

