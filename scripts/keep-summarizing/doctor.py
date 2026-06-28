from core import *
from indexes import markdown_files, open_question_files, v3_note_issues

def cmd_doctor(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    config = project_config(root)
    issues = []
    if (skill_root() / "knowledge").exists():
        issues.append("forbidden bundled runtime knowledge directory: knowledge/")
    if not (root / "project.yaml").exists():
        issues.append("missing project.yaml")
    ids: dict[str, str] = {}
    for path in markdown_files(root):
        fm, _ = read_front_matter(path)
        if not fm:
            issues.append(f"missing front matter: {path.relative_to(root)}")
            continue
        for key in ["id", "title", "perspective", "status", "visibility", "sensitivity", "created_at", "updated_at"]:
            if key not in fm:
                issues.append(f"missing {key}: {path.relative_to(root)}")
        issues.extend(v3_note_issues(root, path, fm))
        nid = str(fm.get("id", ""))
        if nid in ids:
            issues.append(f"duplicate id {nid}: {ids[nid]} and {path.relative_to(root)}")
        elif nid:
            ids[nid] = path.relative_to(root).as_posix()
        perspective = fm.get("perspective")
        if perspective in LEGACY_PERSPECTIVES:
            issues.append(f"legacy broad perspective used in curated note: {path.relative_to(root)}")
        elif perspective and perspective not in LEAF_PERSPECTIVES and perspective not in V3_LEAF_PERSPECTIVES:
            issues.append(f"invalid perspective {perspective}: {path.relative_to(root)}")
        if perspective and perspective in LEAF_PERSPECTIVES and f"notes/{perspective}/" not in path.relative_to(root).as_posix():
            issues.append(f"perspective/path mismatch: {path.relative_to(root)}")
        status = str(fm.get("status", ""))
        if status and status not in config["statuses"]:
            issues.append(f"invalid status {status}: {path.relative_to(root)}")
        sensitivity = str(fm.get("sensitivity", ""))
        if sensitivity and sensitivity not in DEFAULT_SENSITIVITIES:
            issues.append(f"invalid sensitivity {sensitivity}: {path.relative_to(root)}")
    for path in open_question_files(root):
        fm, _ = read_front_matter(path)
        if not fm:
            issues.append(f"missing front matter: {path.relative_to(root)}")
            continue
        for key in ["id", "title", "perspective", "status", "trigger_terms"]:
            if key not in fm:
                issues.append(f"missing {key}: {path.relative_to(root)}")
        status = str(fm.get("status", ""))
        if status and status not in QUESTION_STATUSES:
            issues.append(f"invalid open-question status {status}: {path.relative_to(root)}")
        perspective = fm.get("perspective")
        if perspective in LEGACY_PERSPECTIVES:
            issues.append(f"legacy broad perspective used in open question: {path.relative_to(root)}")
        elif perspective and perspective not in LEAF_PERSPECTIVES and perspective not in V3_LEAF_PERSPECTIVES:
            issues.append(f"invalid open-question perspective {perspective}: {path.relative_to(root)}")
        if perspective and f"open-questions/{perspective}/" not in path.relative_to(root).as_posix():
            issues.append(f"open-question perspective/path mismatch: {path.relative_to(root)}")
    for path in sorted(markdown_files(root) + open_question_files(root)):
        for target in re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", path.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+://", target) or target.startswith("mailto:") or target.startswith("?"):
                continue
            linked = (path.parent / target).resolve()
            if not is_relative_to(linked, root):
                issues.append(f"markdown link escapes knowledge root: {path.relative_to(root)} -> {target}")
            elif not linked.exists():
                issues.append(f"broken markdown link: {path.relative_to(root)} -> {target}")
    skill_paths = [
        path
        for path in skill_root().glob("**/*.md")
        if ".git" not in path.parts and "knowledge" not in path.relative_to(skill_root()).parts
    ]
    for path in sorted(skill_paths):
        for target in re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", path.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+://", target) or target.startswith("mailto:") or target.startswith("?"):
                continue
            linked = (path.parent / target).resolve()
            if not is_relative_to(linked, skill_root()):
                issues.append(f"skill markdown link escapes skill root: {path.relative_to(skill_root())} -> {target}")
            elif not linked.exists():
                issues.append(f"broken skill markdown link: {path.relative_to(skill_root())} -> {target}")
    doc_registry = root / "indexes" / "document-registry.jsonl"
    oq_registry = root / "indexes" / "open-question-registry.jsonl"
    sqlite_registry = root / "indexes" / "knowledge.sqlite"
    vector_status = root / "indexes" / VECTOR_INDEX_STATUS_FILE
    vector_artifact = root / "indexes" / VECTOR_INDEX_ARTIFACT_FILE
    if markdown_files(root) and (not doc_registry.exists() or any(path.stat().st_mtime > doc_registry.stat().st_mtime for path in markdown_files(root))):
        issues.append("stale or missing document indexes")
    if markdown_files(root) and (not sqlite_registry.exists() or any(path.stat().st_mtime > sqlite_registry.stat().st_mtime for path in markdown_files(root))):
        issues.append("stale or missing SQLite FTS index")
    if markdown_files(root) and (not vector_status.exists() or not vector_artifact.exists()):
        issues.append("stale or missing vector index status")
    elif markdown_files(root) and any(path.stat().st_mtime > vector_status.stat().st_mtime for path in markdown_files(root)):
        issues.append("stale or missing vector index status")
    if open_question_files(root) and (not oq_registry.exists() or any(path.stat().st_mtime > oq_registry.stat().st_mtime for path in open_question_files(root))):
        issues.append("stale or missing open-question indexes")
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    if not project_registry_entry(args.project, args):
        print(f"warning: project is not registered: {args.project}")
    print("ok")
