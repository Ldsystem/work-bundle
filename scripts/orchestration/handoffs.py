from core import *
from execution_context import explicit_handoff_plan_identities
from specs import replace_front_matter_value

HANDOFF_EXTENSIONS = (".md", ".yaml", ".yml")


def _handoff_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.glob("*/*/*")
        if path.is_file() and path.suffix in HANDOFF_EXTENSIONS
    )


def _read_compact_yaml_metadata(path: Path) -> dict[str, object]:
    data: dict[str, object] = {}
    related: dict[str, object] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith((" ", "-")):
            if current == "related" and ":" in stripped and not stripped.startswith("-"):
                key, value = stripped.split(":", 1)
                related[key.strip()] = value.strip() or None
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current = key
        if value:
            data[key] = value.strip("'\"")
        elif key == "related":
            data[key] = related
    if related:
        data["related"] = related
    return data


def _read_handoff_metadata(path: Path) -> dict[str, object]:
    if path.suffix == ".md":
        fm, _ = read_front_matter(path)
        return fm
    return _read_compact_yaml_metadata(path)


def _related_value(metadata: dict[str, object], flat_key: str, nested_key: str) -> object:
    if flat_key in metadata:
        return metadata.get(flat_key)
    related = metadata.get("related")
    if isinstance(related, dict):
        return related.get(nested_key)
    return None


def _handoff_sequence_id(root: Path, prefix: str) -> str:
    date = now_date().replace("-", "")
    numbers: list[int] = []
    pattern = re.compile(rf"^{re.escape(prefix)}-{date}-(\d+)")
    for path in root.glob(f"**/{prefix}-{date}-*"):
        if path.suffix not in HANDOFF_EXTENSIONS:
            continue
        match = pattern.match(path.stem)
        if match:
            numbers.append(int(match.group(1)))
    return f"{prefix}-{date}-{(max(numbers) if numbers else 0) + 1:03d}"


def _handoff_identity_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "~"}:
        return None
    return text


def _task_scoped_related(existing: dict[str, object]) -> bool:
    related = existing.get("related") if isinstance(existing.get("related"), dict) else {}
    return bool(_handoff_identity_text(related.get("task")) or _handoff_identity_text(existing.get("related_task")))


def _fill_missing_related_plan(content: str, plan_id: str) -> str:
    lines = content.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("related:"):
            continue
        rest = stripped[len("related:") :].strip()
        if rest.startswith("{") and rest.endswith("}"):
            inner = rest[1:-1].strip()
            lines[index] = f"related: {{plan: {plan_id}, {inner}}}" if inner else f"related: {{plan: {plan_id}}}"
            return "\n".join(lines).rstrip() + "\n"
        if not rest:
            lines.insert(index + 1, f"  plan: {plan_id}")
            return "\n".join(lines).rstrip() + "\n"
    raise SystemExit("Handoff plan identity missing: expected an explicit related.plan")


def _reconcile_task_handoff_plan(content: str, existing: dict[str, object], fields: dict[str, object]) -> str:
    if not _task_scoped_related(existing):
        return content
    identities = explicit_handoff_plan_identities(existing)
    arg_plan = _handoff_identity_text(fields.get("related_plan"))
    if len(identities) > 1:
        raise SystemExit(f"Handoff plan identity conflict: {' vs '.join(identities)}")
    if len(identities) == 1:
        if arg_plan and identities[0] != arg_plan:
            raise SystemExit(f"Handoff plan mismatch: expected {arg_plan}, got {identities[0]}")
        return content
    if not arg_plan:
        raise SystemExit("Handoff plan identity missing: expected an explicit related.plan")
    return _fill_missing_related_plan(content, arg_plan)


def _ensure_yaml_metadata(content: str, fields: dict[str, object]) -> str:
    existing = _read_compact_yaml_metadata_from_text(content)
    lines: list[str] = []
    for key in ("id", "type", "status", "project", "created_at", "updated_at"):
        if key not in existing:
            lines.append(f"{key}: {fields[key]}")
    if "related" not in existing:
        lines.extend(
            [
                "related:",
                f"  spec: {fields['related_spec']}",
                f"  plan: {fields['related_plan']}",
                f"  phase: {fields['related_phase']}",
                f"  task: {fields['related_task']}",
            ]
        )
    else:
        content = _reconcile_task_handoff_plan(content, existing, fields)
    if not lines:
        return content
    return "\n".join(lines) + "\n\n" + content.strip() + "\n"


def _read_compact_yaml_metadata_from_text(text: str) -> dict[str, object]:
    data: dict[str, object] = {}
    related: dict[str, object] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith((" ", "-")):
            if current == "related" and ":" in stripped and not stripped.startswith("-"):
                key, value = stripped.split(":", 1)
                related[key.strip()] = value.strip() or None
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current = key
        if value:
            data[key] = value.strip("'\"")
        elif key == "related":
            data[key] = related
    if related:
        data["related"] = related
    return data


def _replace_yaml_top_level_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            lines[index] = f"{key}: {value}"
            break
    else:
        lines.insert(0, f"{key}: {value}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def index_handoffs(args: argparse.Namespace) -> list[dict[str, object]]:
    root = orchestration_root(args) / "handoff"
    rows = []
    for path in _handoff_paths(root):
        metadata = _read_handoff_metadata(path)
        if not metadata:
            continue
        rows.append({"id": metadata.get("id", path.stem), "type": metadata.get("type", ""), "status": metadata.get("status", "active"), "path": rel(path, args), "project": metadata.get("project", ""), "created_at": metadata.get("created_at", ""), "updated_at": metadata.get("updated_at", ""), "related_spec": _related_value(metadata, "related_spec", "spec"), "related_plan": _related_value(metadata, "related_plan", "plan"), "related_phase": _related_value(metadata, "related_phase", "phase"), "related_task": _related_value(metadata, "related_task", "task")})
    (root / "index.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
    return rows


def cmd_write_handoff(args: argparse.Namespace) -> None:
    init_dirs(args)
    if args.type not in HANDOFF_TYPES:
        raise SystemExit(f"Invalid handoff type: {args.type}")
    if args.status not in HANDOFF_STATUSES:
        raise SystemExit(f"Invalid handoff status: {args.status}")
    if args.type == "orchestration" and args.status != "archived":
        raise SystemExit("Active orchestration handoff creation is retired; use executor-result handoffs.")
    hprefix = "handoff-orch" if args.type == "orchestration" else "handoff-exec"
    hid = args.id or _handoff_sequence_id(orchestration_root(args) / "handoff", hprefix)
    folder = "orchestration" if args.type == "orchestration" else "executor"
    content = Path(args.content_file).read_text(encoding="utf-8")
    fields = {"id": hid, "type": args.type, "title": args.title, "status": args.status, "project": project_root(args).name, "created_at": now_date(), "updated_at": now_date(), "related_spec": args.related_spec or "null", "related_plan": args.related_plan or "null", "related_phase": args.related_phase or "null", "related_task": args.related_task or "null"}
    handoff_format = args.format or ("yaml" if args.type == "executor-result" else "markdown")
    if handoff_format == "yaml" and args.type != "executor-result":
        raise SystemExit("YAML handoff writing is only supported for executor-result handoffs.")
    content = _ensure_yaml_metadata(content, fields) if handoff_format == "yaml" else ensure_front_matter(content, fields)
    target_status_dir = "archived" if args.status == "archived" else "active"
    suffix = ".yaml" if handoff_format == "yaml" else ".md"
    target = orchestration_root(args) / "handoff" / folder / target_status_dir / f"{hid}-{slugify(args.title)}{suffix}"
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
    if path.suffix == ".md":
        replace_front_matter_value(path, "status", args.status)
    elif path.suffix in {".yaml", ".yml"}:
        _replace_yaml_top_level_value(path, "status", args.status)
    else:
        raise SystemExit(f"Unsupported handoff extension: {path}")
    if args.status == "archived":
        folder = "orchestration" if match.get("type") == "orchestration" else "executor"
        active_root = orchestration_root(args) / "handoff" / folder / "active"
        archived_root = orchestration_root(args) / "handoff" / folder / "archived"
        if is_relative_to(path, active_root):
            move_to_archive(path, active_root, archived_root)
    index_handoffs(args)
    print(args.id)
