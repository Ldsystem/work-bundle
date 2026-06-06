from core import *

def index_specs(args: argparse.Namespace) -> list[dict[str, object]]:
    root = orchestration_root(args) / "spec"
    rows = []
    for path in sorted(root.glob("*/*.md")):
        fm, _ = read_front_matter(path)
        if not fm:
            continue
        rows.append(
            {
                "type": "spec",
                "id": fm.get("id", path.stem),
                "title": fm.get("title", path.stem),
                "status": fm.get("status", "draft"),
                "path": rel(path, args),
                "purpose": fm.get("purpose", ""),
                "component": fm.get("component", ""),
                "created_at": fm.get("date_created", fm.get("created_at", "")),
                "updated_at": fm.get("last_updated", fm.get("updated_at", "")),
            }
        )
    target = root / "index.jsonl"
    target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
    return rows


def cmd_index_specs(args: argparse.Namespace) -> None:
    print(f"indexed {len(index_specs(args))} specs")


def cmd_write_spec(args: argparse.Namespace) -> None:
    init_dirs(args)
    if args.status not in SPEC_STATUSES:
        raise SystemExit(f"Invalid spec status: {args.status}")
    root = orchestration_root(args) / "spec" / ("archived" if args.status == "archived" else "active")
    sid = args.id or sequence_id(root, "spec")
    filename = args.filename or f"{sid}-{slugify(args.title)}.md"
    content = Path(args.content_file).read_text(encoding="utf-8")
    content = ensure_front_matter(
        content,
        {
            "id": sid,
            "title": args.title,
            "status": args.status,
            "date_created": now_date(),
            "last_updated": now_date(),
            "purpose": args.purpose,
            "component": args.component,
            "version": args.version,
        },
    )
    target = root / filename
    write_text_safely(target, content, args)
    index_specs(args)
    print(rel(target, args))


def load_index(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_list_specs(args: argparse.Namespace) -> None:
    rows = index_specs(args)
    for row in rows:
        if args.status and row.get("status") != args.status:
            continue
        print(json.dumps(row, ensure_ascii=False))


def replace_front_matter_value(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"Missing front matter: {path}")
    end = text.find("\n---\n", 4)
    raw = text[4:end]
    body = text[end + 5 :]
    lines = []
    replaced = False
    for line in raw.splitlines():
        if line.startswith(f"{key}:"):
            lines.append(f"{key}: {value}")
            replaced = True
        elif line.startswith("last_updated:") or line.startswith("updated_at:"):
            lines.append(f"{line.split(':', 1)[0]}: {now_date()}")
        else:
            lines.append(line)
    if not replaced:
        lines.append(f"{key}: {value}")
    path.write_text("---\n" + "\n".join(lines) + "\n---\n" + body, encoding="utf-8")


def cmd_set_spec_status(args: argparse.Namespace) -> None:
    if args.status not in SPEC_STATUSES:
        raise SystemExit(f"Invalid spec status: {args.status}")
    rows = index_specs(args)
    match = next((row for row in rows if row.get("id") == args.id), None)
    if not match:
        raise SystemExit(f"Spec not found: {args.id}")
    path = project_root(args) / str(match["path"])
    replace_front_matter_value(path, "status", args.status)
    if args.status == "archived":
        target = orchestration_root(args) / "spec" / "archived" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
    index_specs(args)
    print(args.id)

