import hashlib
import os
import tempfile

from core import *
from execution_context import explicit_handoff_plan_identities
from specs import replace_front_matter_value

HANDOFF_EXTENSIONS = (".md", ".yaml", ".yml")
LIFECYCLE_AUTHORITY = "location-v1"
LEGACY_OVERRIDE_KEYS = {
    "handoff_id", "sha256", "type", "related_plan", "related_task", "status"
}
HANDOFF_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


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


def _explicit_related_identities(
    metadata: dict[str, object], flat_key: str, nested_key: str
) -> list[str]:
    related = metadata.get("related") if isinstance(metadata.get("related"), dict) else {}
    identities: list[str] = []
    for raw in (related.get(nested_key), metadata.get(flat_key)):
        value = _handoff_identity_text(raw)
        if value and value not in identities:
            identities.append(value)
    return identities


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
    for key in (
        "id", "type", "status", "lifecycle_authority", "project", "created_at", "updated_at"
    ):
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


def _status_location(path: Path, root: Path) -> tuple[str, str]:
    try:
        folder, status, _name = path.resolve().relative_to(root.resolve()).parts
    except (ValueError, TypeError) as error:
        raise SystemExit(f"Handoff path is outside the lifecycle store: {path}") from error
    if status not in HANDOFF_STATUSES:
        raise SystemExit(f"Invalid handoff status location: {status}")
    return folder, status


def _legacy_overrides(root: Path) -> dict[str, tuple[Path, dict[str, object]]]:
    override_root = root / "legacy-status-overrides"
    records: dict[str, tuple[Path, dict[str, object]]] = {}
    for path in sorted(override_root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(f"Invalid legacy handoff status override: {path}") from error
        if not isinstance(value, dict) or set(value) != LEGACY_OVERRIDE_KEYS:
            raise SystemExit(f"Invalid legacy handoff status override shape: {path}")
        handoff_id = str(value.get("handoff_id") or "")
        if not handoff_id or path.stem != handoff_id:
            raise SystemExit(f"Legacy handoff status override identity mismatch: {path}")
        if handoff_id in records:
            raise SystemExit(f"Duplicate legacy handoff status override identity: {handoff_id}")
        records[handoff_id] = (path, value)
    return records


def _resolved_handoff_status(
    path: Path,
    metadata: dict[str, object],
    location_status: str,
    override: tuple[Path, dict[str, object]] | None,
) -> str:
    marked = metadata.get("lifecycle_authority") == LIFECYCLE_AUTHORITY
    if marked:
        if override is not None:
            raise SystemExit(
                f"Marked handoff has an invalid legacy status override: {metadata.get('id', path.stem)}"
            )
        return location_status
    if metadata.get("lifecycle_authority") not in (None, ""):
        raise SystemExit(f"Invalid handoff lifecycle authority: {metadata.get('lifecycle_authority')}")
    if override is not None:
        _override_path, record = override
        related_plan = _related_value(metadata, "related_plan", "plan")
        related_task = _related_value(metadata, "related_task", "task")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if (
            record.get("sha256") != digest
            or record.get("type") != metadata.get("type")
            or record.get("related_plan") != related_plan
            or record.get("related_task") != related_task
            or record.get("status") not in HANDOFF_STATUSES
            or record.get("status") != location_status
        ):
            raise SystemExit(
                f"Legacy handoff status override contradicts digest, binding, or location: {record.get('handoff_id')}"
            )
        return str(record["status"])
    if location_status != "active":
        return location_status
    embedded = str(metadata.get("status") or "active")
    if embedded not in HANDOFF_STATUSES:
        raise SystemExit(f"Invalid legacy embedded handoff status: {embedded}")
    return embedded


def _collect_handoff_rows(args: argparse.Namespace) -> list[dict[str, object]]:
    root = orchestration_root(args) / "handoff"
    overrides = _legacy_overrides(root)
    rows: list[dict[str, object]] = []
    seen: dict[str, list[tuple[Path, dict[str, object], str, str]]] = {}
    for path in _handoff_paths(root):
        metadata = _read_handoff_metadata(path)
        if not metadata:
            continue
        if metadata.get("lifecycle_authority") == LIFECYCLE_AUTHORITY and not metadata.get("id"):
            raise SystemExit(f"Marked handoff is missing identity: {path}")
        handoff_id = str(metadata.get("id") or path.stem)
        folder, location_status = _status_location(path, root)
        handoff_type = str(metadata.get("type") or "")
        expected_folder = "orchestration" if handoff_type == "orchestration" else "executor"
        if handoff_type not in HANDOFF_TYPES or folder != expected_folder:
            raise SystemExit(f"Handoff type/folder disagreement: {handoff_id}")
        plan_identities = explicit_handoff_plan_identities(metadata)
        if len(plan_identities) > 1:
            raise SystemExit(f"Handoff plan identity conflict: {' vs '.join(plan_identities)}")
        task_identities = _explicit_related_identities(metadata, "related_task", "task")
        if len(task_identities) > 1:
            raise SystemExit(f"Handoff task identity conflict: {' vs '.join(task_identities)}")
        prior = seen.setdefault(handoff_id, [])
        if prior:
            candidates = [*prior, (path, metadata, folder, location_status)]
            colocated_unmarked_legacy = (
                handoff_id not in overrides
                and len({(item[2], item[3]) for item in candidates}) == 1
                and all(
                    item[1].get("lifecycle_authority") in (None, "")
                    for item in candidates
                )
            )
            if not colocated_unmarked_legacy:
                raise SystemExit(
                    f"Duplicate handoff identity across lifecycle locations: {handoff_id}"
                )
        prior.append((path, metadata, folder, location_status))
        current_status = _resolved_handoff_status(
            path, metadata, location_status, overrides.get(handoff_id)
        )
        rows.append({"id": handoff_id, "type": handoff_type, "status": current_status, "path": rel(path, args), "project": metadata.get("project", ""), "created_at": metadata.get("created_at", ""), "updated_at": metadata.get("updated_at", ""), "related_spec": _related_value(metadata, "related_spec", "spec"), "related_plan": _related_value(metadata, "related_plan", "plan"), "related_phase": _related_value(metadata, "related_phase", "phase"), "related_task": _related_value(metadata, "related_task", "task")})
    orphans = sorted(set(overrides) - set(seen))
    if orphans:
        raise SystemExit(f"Legacy handoff status override has no handoff: {', '.join(orphans)}")
    return rows


def index_handoffs(args: argparse.Namespace) -> list[dict[str, object]]:
    root = orchestration_root(args) / "handoff"
    rows = _collect_handoff_rows(args)
    _atomic_text(
        root / "index.jsonl",
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
    )
    return rows


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content if not content or content.endswith("\n") else content + "\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _managed_creation_admission(args: argparse.Namespace, content: str) -> None:
    root = resolve_workspace_root(args)
    if not (root / ".work-bundle/project.yaml").is_file():
        return
    from artifact_inputs import parse_yaml_subset
    from execution_context import _compile_task_brief, validate_executor_result_creation_for_task

    handoff = parse_yaml_subset(content)
    related = handoff.get("related") if isinstance(handoff.get("related"), dict) else {}
    task_id = str(related.get("task") or handoff.get("related_task") or "")
    plan_id = str(related.get("plan") or handoff.get("related_plan") or "")
    if not task_id or not plan_id:
        raise SystemExit("Managed executor-result creation requires related.plan and related.task")
    plan_root = root / ".work-bundle/orchestration/plan"
    candidates = [
        path
        for status in ("active", "archived")
        for path in (plan_root / status).glob("**/*.md")
        if path.name.startswith("task-")
    ]
    matches: list[Path] = []
    from artifact_inputs import _read_structured
    for path in candidates:
        task, _body = _read_structured(path)
        if str(task.get("id") or "") == task_id and str(task.get("plan_id") or "") == plan_id:
            matches.append(path)
    if len(matches) != 1:
        raise SystemExit(f"Expected one task {plan_id}/{task_id} for handoff creation; found {len(matches)}")
    compile_args = argparse.Namespace(
        project_root=getattr(args, "project_root", None),
        workspace_id=getattr(args, "workspace_id", None),
        execution_id=getattr(args, "execution_id", None),
        repository_id=getattr(args, "repository_id", None),
        execution_runtime_root=getattr(args, "execution_runtime_root", None),
        task=str(matches[0]), handoff=None, base=None, head=None,
    )
    _path, document = _compile_task_brief(compile_args)
    validate_executor_result_creation_for_task(handoff, document["task_brief"])


def _assert_new_executor_metadata(
    content: str, *, handoff_id: str, handoff_type: str, status: str
) -> None:
    metadata = _read_compact_yaml_metadata_from_text(content)
    expected = {
        "id": handoff_id,
        "type": handoff_type,
        "status": status,
        "lifecycle_authority": LIFECYCLE_AUTHORITY,
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            raise SystemExit(
                f"Handoff creation metadata mismatch for {field}: "
                f"expected {value}, got {metadata.get(field) or 'missing'}"
            )


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
    if not HANDOFF_ID_RE.fullmatch(str(hid)):
        raise SystemExit(f"Invalid handoff identity: {hid}")
    folder = "orchestration" if args.type == "orchestration" else "executor"
    content = Path(args.content_file).read_text(encoding="utf-8")
    fields = {"id": hid, "type": args.type, "title": args.title, "status": args.status, "lifecycle_authority": LIFECYCLE_AUTHORITY, "project": project_root(args).name, "created_at": now_date(), "updated_at": now_date(), "related_spec": args.related_spec or "null", "related_plan": args.related_plan or "null", "related_phase": args.related_phase or "null", "related_task": args.related_task or "null"}
    handoff_format = args.format or ("yaml" if args.type == "executor-result" else "markdown")
    if handoff_format == "yaml" and args.type != "executor-result":
        raise SystemExit("YAML handoff writing is only supported for executor-result handoffs.")
    content = _ensure_yaml_metadata(content, fields) if handoff_format == "yaml" else ensure_front_matter(content, fields)
    if args.type == "executor-result":
        _assert_new_executor_metadata(
            content, handoff_id=str(hid), handoff_type=args.type, status=args.status
        )
        _managed_creation_admission(args, content)
    rows = _collect_handoff_rows(args)
    if any(row.get("id") == hid for row in rows):
        raise SystemExit(f"Duplicate handoff identity across lifecycle locations: {hid}")
    target_status_dir = args.status
    suffix = ".yaml" if handoff_format == "yaml" else ".md"
    target = orchestration_root(args) / "handoff" / folder / target_status_dir / f"{hid}-{slugify(args.title)}{suffix}"
    if target.exists():
        raise SystemExit(f"Handoff lifecycle target already exists: {target}")
    index_path = orchestration_root(args) / "handoff/index.jsonl"
    previous_index = index_path.read_bytes() if index_path.is_file() else None
    try:
        _atomic_text(target, content)
        index_handoffs(args)
    except BaseException:
        target.unlink(missing_ok=True)
        if previous_index is None:
            index_path.unlink(missing_ok=True)
        else:
            index_path.write_bytes(previous_index)
        raise
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
    if not HANDOFF_ID_RE.fullmatch(str(args.id)):
        raise SystemExit(f"Invalid handoff identity: {args.id}")
    rows = _collect_handoff_rows(args)
    matches = [row for row in rows if row.get("id") == args.id]
    if not matches:
        raise SystemExit(f"Handoff not found: {args.id}")
    if len(matches) != 1:
        raise SystemExit(f"Handoff identity is ambiguous for lifecycle operation: {args.id}")
    match = matches[0]
    path = artifact_path_from_row(match, args)
    if match.get("status") == args.status:
        print(args.id)
        return
    metadata = _read_handoff_metadata(path)
    folder = "orchestration" if match.get("type") == "orchestration" else "executor"
    target = orchestration_root(args) / "handoff" / folder / args.status / path.name
    if target.exists() and target.resolve() != path.resolve():
        raise SystemExit(f"Handoff lifecycle target already exists: {target}")
    marked = metadata.get("lifecycle_authority") == LIFECYCLE_AUTHORITY
    override_path = orchestration_root(args) / "handoff/legacy-status-overrides" / f"{args.id}.json"
    old_override = override_path.read_bytes() if override_path.is_file() else None
    index_path = orchestration_root(args) / "handoff/index.jsonl"
    old_index = index_path.read_bytes() if index_path.is_file() else None
    moved = target.resolve() != path.resolve()
    try:
        if moved:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, target)
        if not marked:
            record = {
                "handoff_id": str(args.id),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "type": metadata.get("type"),
                "related_plan": _related_value(metadata, "related_plan", "plan"),
                "related_task": _related_value(metadata, "related_task", "task"),
                "status": args.status,
            }
            _atomic_text(override_path, json.dumps(record, sort_keys=True))
        index_handoffs(args)
    except BaseException:
        if moved and target.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target, path)
        if old_override is None:
            override_path.unlink(missing_ok=True)
        else:
            override_path.write_bytes(old_override)
        if old_index is None:
            index_path.unlink(missing_ok=True)
        else:
            index_path.write_bytes(old_index)
        raise
    print(args.id)
