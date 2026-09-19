from core import *
from indexes import markdown_files



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
