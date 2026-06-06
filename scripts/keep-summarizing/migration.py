from core import *
from indexes import cmd_index, markdown_files
from registry import upsert_registry_project

LEGACY_PERSPECTIVE_MAP = {
    "architecture": "architecture/component-boundary",
    "code-structure": "implementation/backend/module-structure",
    "data-flow": "workflow/data-flow",
    "decisions": "architecture/decisions",
    "glossary": "background/glossary",
    "patterns": "architecture/patterns",
    "process-flow": "workflow/process-flow",
}


def remap_legacy_markdown(text: str, perspective: str) -> str:
    mapped = LEGACY_PERSPECTIVE_MAP.get(perspective, perspective)
    return re.sub(rf"^perspective:\s*{re.escape(perspective)}\s*$", f"perspective: {mapped}", text, flags=re.MULTILINE)


def copy_tree_markdown(source: Path, target: Path, remap_legacy_perspectives: bool = False) -> int:
    count = 0
    if not source.exists():
        return count
    for path in sorted(source.glob("**/*.md")):
        rel = path.relative_to(source)
        text = path.read_text(encoding="utf-8")
        if remap_legacy_perspectives and rel.parts:
            first = rel.parts[0]
            if first in LEGACY_PERSPECTIVE_MAP:
                mapped = Path(LEGACY_PERSPECTIVE_MAP[first])
                rel = mapped / Path(*rel.parts[1:])
                text = remap_legacy_markdown(text, first)
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_text(text, encoding="utf-8")
            count += 1
    return count


def cmd_migrate_legacy(args: argparse.Namespace) -> None:
    destination = project_dir(args.project, args)
    legacy_base = Path(args.legacy_root).resolve() if args.legacy_root else knowledge_root().resolve()
    legacy = (legacy_base / args.project).resolve()
    if not legacy.exists():
        raise SystemExit(f"Legacy knowledge repo not found: {legacy}")
    destination.mkdir(parents=True, exist_ok=True)
    legacy_project_yaml = legacy / "project.yaml"
    if legacy_project_yaml.exists():
        project_yaml = legacy_project_yaml.read_text(encoding="utf-8").replace(f"knowledge/{args.project}", ".work-bundle/knowledge")
        (destination / "project.yaml").write_text(project_yaml, encoding="utf-8")
    elif not (destination / "project.yaml").exists():
        write_project_yaml(destination, args.project, None)
    migrated = 0
    migrated += copy_tree_markdown(legacy / "notes", destination / "notes", remap_legacy_perspectives=True)
    migrated += copy_tree_markdown(legacy / "open-questions", destination / "open-questions", remap_legacy_perspectives=True)
    migrated += copy_tree_markdown(legacy / "context-packs", destination / "context-packs")
    handoff_source = legacy / "handoffs"
    if handoff_source.exists():
        project_root = Path(getattr(args, "project_root", "") or os.getcwd()).resolve()
        handoff_target = project_root / ".work-bundle" / "orchestration" / "handoff" / "orchestration" / "active"
        migrated += copy_tree_markdown(handoff_source, handoff_target)
    cmd_index(args)
    project_root = Path(getattr(args, "project_root", "") or destination.parent.parent).resolve()
    upsert_registry_project(args.project, project_root, args, name=args.project, sources=[str(project_root)])
    print(f"migrated {migrated} markdown files")



def candidate_v3_classification(path: Path, root: Path, fm: dict[str, object]) -> dict[str, object]:
    rel = path.relative_to(root).as_posix()
    perspective = str(fm.get("perspective", "")).strip("/")
    first = perspective.split("/", 1)[0] if perspective else ""
    lifecycle = lifecycle_from_perspective(perspective) if is_v3_perspective(perspective) else "development_design"
    target_leaf = perspective.split("/", 1)[1] if is_v3_perspective(perspective) else perspective
    target_perspective = perspective if is_v3_perspective(perspective) else f"{lifecycle_to_path_segment(lifecycle)}/{target_leaf or 'architecture/decisions'}"
    status = str(fm.get("status", "draft"))
    if status not in DEFAULT_STATUSES:
        status = "draft"
    if first in LEGACY_PERSPECTIVES or not perspective:
        action = "manual_classification_required"
        confidence = "low"
    elif is_v3_perspective(perspective):
        action = "keep"
        confidence = "high"
    else:
        action = "move"
        confidence = "medium"
    return {
        "old_path": rel,
        "title": fm.get("title", path.stem),
        "old_perspective": perspective,
        "candidate_lifecycle_stage": lifecycle,
        "candidate_perspective": target_perspective,
        "candidate_status": status,
        "confidence": confidence,
        "reason": "dry-run v3 classification; mixed lifecycle content still requires human review",
        "action": action,
    }


def cmd_migrate_v3(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    migration_root = root / "migration"
    migration_root.mkdir(parents=True, exist_ok=True)
    records = []
    for path in markdown_files(root):
        if not path.relative_to(root).as_posix().startswith("notes/"):
            continue
        fm, _ = read_front_matter(path)
        if not fm:
            continue
        records.append(candidate_v3_classification(path, root, fm))
    target = migration_root / "v3-inventory.jsonl"
    target.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + ("\n" if records else ""), encoding="utf-8")
    print(f"wrote {len(records)} inventory records to {target}")

