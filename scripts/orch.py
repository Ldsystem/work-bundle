#!/usr/bin/env python3
"""Deterministic helpers for the orchestrator skill."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
from pathlib import Path


SPEC_STATUSES = {"draft", "active", "implemented", "reviewed", "superseded", "archived"}
PLAN_STATUSES = {"Planned", "In progress", "Completed", "Deprecated", "On Hold"}
HANDOFF_STATUSES = {"active", "reviewed", "archived", "superseded"}
HANDOFF_TYPES = {"orchestration", "executor-result"}
RETRIEVAL_ROLES = {"authority", "candidate", "background", "blocked"}
DIRECTIVE_POLICY_MAP = {
    "create-specification": "implementation_spec",
    "create-implementation-plan": "implementation_plan",
    "create-document": "customer_spec",
    "create-handoff": "implementation_plan",
    "review-plan": "implementation_plan",
    "execute-plan": "execution",
    "customer-spec": "customer_spec",
    "bidding": "bidding",
    "deployment": "deployment",
    "operation": "operation",
}


def now_date() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-") or "untitled"


def is_relative_to(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


def project_root(args: argparse.Namespace) -> Path:
    if args.project_root:
        return Path(args.project_root).resolve()
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".work-bundle").exists():
            return candidate
    raise SystemExit("No project root found. Pass --project-root or run inside a work bundle.")


def work_bundle(args: argparse.Namespace) -> Path:
    return project_root(args) / ".work-bundle"


def orchestration_root(args: argparse.Namespace) -> Path:
    return work_bundle(args) / "orchestration"


def ensure_under_orchestration(path: Path, args: argparse.Namespace) -> Path:
    resolved = path.resolve()
    allowed = orchestration_root(args).resolve()
    if not is_relative_to(resolved, allowed):
        raise SystemExit(f"Path escapes orchestration root: {resolved}")
    if ".work-bundle/knowledge" in resolved.as_posix():
        raise SystemExit(f"Orchestrator must not write durable knowledge: {resolved}")
    return resolved


def read_front_matter(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    data: dict[str, object] = {}
    for line in raw.splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data, body


def write_text_safely(path: Path, content: str, args: argparse.Namespace) -> None:
    target = ensure_under_orchestration(path, args)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + "\n", encoding="utf-8")


def sequence_id(root: Path, prefix: str) -> str:
    date = now_date().replace("-", "")
    existing = sorted(root.glob(f"**/{prefix}-{date}-*.md"))
    return f"{prefix}-{date}-{len(existing) + 1:03d}"


def ensure_front_matter(content: str, fields: dict[str, object]) -> str:
    if content.startswith("---\n"):
        return content
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + content.strip() + "\n"


def init_dirs(args: argparse.Namespace) -> None:
    root = orchestration_root(args)
    for directory in [
        "spec/active",
        "spec/archived",
        "plan/active",
        "plan/archived",
        "handoff/orchestration/active",
        "handoff/orchestration/archived",
        "handoff/executor/active",
        "handoff/executor/archived",
        "docs",
    ]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    for index in ["spec/index.jsonl", "plan/index.jsonl", "handoff/index.jsonl"]:
        path = root / index
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)


def rel(path: Path, args: argparse.Namespace) -> str:
    return path.resolve().relative_to(project_root(args)).as_posix()


def artifact_path_from_row(row: dict[str, object], args: argparse.Namespace) -> Path:
    raw_path = str(row.get("path", ""))
    if not raw_path:
        raise SystemExit(f"Index row has no path: {row}")
    return project_root(args) / raw_path


def move_to_archive(path: Path, active_root: Path, archived_root: Path) -> Path:
    relative = path.resolve().relative_to(active_root.resolve())
    target = archived_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    return target


def count_by_status(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def policy_for_directive(name: str) -> str:
    if name not in DIRECTIVE_POLICY_MAP:
        raise SystemExit(f"Unknown retrieval policy for directive: {name}")
    return DIRECTIVE_POLICY_MAP[name]


def artifact_mentions_retrieval_without_roles(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "retrieval" not in text.lower():
        return False
    return not any(role in text for role in RETRIEVAL_ROLES)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def keep_summarizing_root() -> Path:
    return repository_root() / "keep-summarizing"


def cmd_init(args: argparse.Namespace) -> None:
    init_dirs(args)
    print(str(orchestration_root(args)))


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


def cmd_write_doc(args: argparse.Namespace) -> None:
    init_dirs(args)
    content = Path(args.content_file).read_text(encoding="utf-8")
    target = orchestration_root(args) / "docs" / f"{slugify(args.title)}.md"
    write_text_safely(target, content, args)
    print(rel(target, args))


def cmd_state(args: argparse.Namespace) -> None:
    init_dirs(args)
    state = {
        "specs": count_by_status(index_specs(args)),
        "plans": count_by_status(index_plans(args)),
        "handoffs": count_by_status(index_handoffs(args)),
        "docs": len(list((orchestration_root(args) / "docs").glob("*.md"))),
    }
    print(json.dumps(state, ensure_ascii=False))


def cmd_related(args: argparse.Namespace) -> None:
    init_dirs(args)
    rows = []
    for index in ["spec/index.jsonl", "plan/index.jsonl", "handoff/index.jsonl"]:
        rows.extend(load_index(orchestration_root(args) / index))
    for row in rows:
        if args.id in json.dumps(row, ensure_ascii=False):
            print(json.dumps(row, ensure_ascii=False))


def cmd_next_action_candidates(args: argparse.Namespace) -> None:
    init_dirs(args)
    for row in index_handoffs(args):
        if row.get("type") == "executor-result" and row.get("status") == "active":
            print(json.dumps({"action": "review-executor-handoff", "handoff_id": row.get("id"), "reason": "active executor handoff exists"}, ensure_ascii=False))
    for row in index_plans(args):
        if row.get("type") == "task" and row.get("status") in {"Planned", "In progress"}:
            print(json.dumps({"action": "continue-task", "task_id": row.get("id"), "plan_id": row.get("plan_id"), "phase_id": row.get("phase_id"), "reason": "task is executable or in progress"}, ensure_ascii=False))


def cmd_git_status(args: argparse.Namespace) -> None:
    root = project_root(args)
    git = root / ".git"
    if not git.exists():
        print(json.dumps({"git": "absent", "project_root": str(root)}, ensure_ascii=False))
        return
    print(json.dumps({"git": "present", "project_root": str(root)}, ensure_ascii=False))


def cmd_doctor(args: argparse.Namespace) -> None:
    init_dirs(args)
    issues = []
    root = orchestration_root(args)
    for required in ["spec/active", "spec/archived", "spec/index.jsonl", "plan/active", "plan/archived", "plan/index.jsonl", "handoff/orchestration/active", "handoff/orchestration/archived", "handoff/executor/active", "handoff/executor/archived", "handoff/index.jsonl", "docs"]:
        if not (root / required).exists():
            issues.append(f"missing {required}")
    seen = set()
    for index in ["spec/index.jsonl", "plan/index.jsonl", "handoff/index.jsonl"]:
        for row in load_index(root / index):
            rid = str(row.get("id", ""))
            if rid in seen:
                issues.append(f"duplicate id {rid}")
            seen.add(rid)
            path = project_root(args) / str(row.get("path", ""))
            if not is_relative_to(path, root):
                issues.append(f"index path escapes orchestration root: {row}")
    for path in root.glob("**/*.md"):
        if ".work-bundle/knowledge" in path.resolve().as_posix():
            issues.append(f"artifact under knowledge root: {path}")
        if artifact_mentions_retrieval_without_roles(path):
            issues.append(f"retrieval artifact lacks role labels: {path.relative_to(root)}")
    directive_root = Path(__file__).resolve().parents[1] / "references" / "directives"
    knowledge_directives = {"create-specification", "create-implementation-plan", "create-document", "create-handoff", "review-plan", "execute-plan"}
    for directive in knowledge_directives:
        path = directive_root / f"{directive}.md"
        if not path.exists():
            issues.append(f"missing directive file for policy check: {directive}")
            continue
        text = path.read_text(encoding="utf-8")
        if directive == "execute-plan":
            if "must not run v3 retrieval" not in text and "must not invoke retrieval" not in text:
                issues.append("execute-plan lacks explicit no-retrieval rule")
        elif directive not in DIRECTIVE_POLICY_MAP:
            issues.append(f"missing retrieval policy mapping: {directive}")
        elif DIRECTIVE_POLICY_MAP[directive] not in text and "Knowledge Gateway" in text:
            issues.append(f"directive does not mention mapped retrieval policy {DIRECTIVE_POLICY_MAP[directive]}: {directive}")
    ks_root = keep_summarizing_root()
    what_is_helpful = ks_root / "references" / "directives" / "what-is-helpful.md"
    if not what_is_helpful.exists():
        issues.append("missing keep-summarizing what-is-helpful directive")
    else:
        text = what_is_helpful.read_text(encoding="utf-8")
        for required in ["Gateway mode", "ks.py query", "retrieval_role", "authority", "candidate", "background", "blocked"]:
            if required not in text:
                issues.append(f"what-is-helpful missing gateway contract term: {required}")
    for path in [ks_root / "SKILL.md", ks_root / "README.md", ks_root / "references" / "workflow.md"]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if "notes/<leaf-perspective>" in text or "status: archived" in text:
                issues.append(f"keep-summarizing doc advertises legacy path/status: {path.relative_to(ks_root)}")
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print("ok")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--project-root")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", parents=[parent]).set_defaults(func=cmd_init)
    sub.add_parser("doctor", parents=[parent]).set_defaults(func=cmd_doctor)
    sub.add_parser("state", parents=[parent]).set_defaults(func=cmd_state)
    sub.add_parser("next-action-candidates", parents=[parent]).set_defaults(func=cmd_next_action_candidates)
    sub.add_parser("git-status", parents=[parent]).set_defaults(func=cmd_git_status)
    related = sub.add_parser("related", parents=[parent])
    related.add_argument("--id", required=True)
    related.set_defaults(func=cmd_related)
    write_doc = sub.add_parser("write-doc", parents=[parent])
    write_doc.add_argument("--title", required=True)
    write_doc.add_argument("--content-file", required=True)
    write_doc.set_defaults(func=cmd_write_doc)
    write_spec = sub.add_parser("write-spec", parents=[parent])
    write_spec.add_argument("--title", required=True)
    write_spec.add_argument("--purpose", required=True)
    write_spec.add_argument("--component", required=True)
    write_spec.add_argument("--version", default="1")
    write_spec.add_argument("--content-file", required=True)
    write_spec.add_argument("--status", default="draft")
    write_spec.add_argument("--id")
    write_spec.add_argument("--filename")
    write_spec.set_defaults(func=cmd_write_spec)
    list_specs = sub.add_parser("list-specs", parents=[parent])
    list_specs.add_argument("--status")
    list_specs.set_defaults(func=cmd_list_specs)
    set_spec = sub.add_parser("set-spec-status", parents=[parent])
    set_spec.add_argument("--id", required=True)
    set_spec.add_argument("--status", required=True)
    set_spec.set_defaults(func=cmd_set_spec_status)
    sub.add_parser("index-specs", parents=[parent]).set_defaults(func=cmd_index_specs)
    write_plan = sub.add_parser("write-plan", parents=[parent])
    write_plan.add_argument("--title", required=True)
    write_plan.add_argument("--purpose", required=True)
    write_plan.add_argument("--component", required=True)
    write_plan.add_argument("--version", default="1")
    write_plan.add_argument("--content-file", required=True)
    write_plan.add_argument("--status", default="Planned")
    write_plan.add_argument("--id")
    write_plan.add_argument("--filename")
    write_plan.set_defaults(func=cmd_write_plan)
    list_plans = sub.add_parser("list-plans", parents=[parent])
    list_plans.add_argument("--status")
    list_plans.add_argument("--kind", choices=["plan", "phase", "task"])
    list_plans.set_defaults(func=cmd_list_plans)
    set_plan = sub.add_parser("set-plan-status", parents=[parent])
    set_plan.add_argument("--id", required=True)
    set_plan.add_argument("--status", required=True)
    set_plan.add_argument("--kind", choices=["plan", "phase", "task"])
    set_plan.set_defaults(func=cmd_set_plan_status)
    archive_plan = sub.add_parser("archive-plan", parents=[parent])
    archive_plan.add_argument("--id", required=True)
    archive_plan.set_defaults(func=cmd_archive_plan)
    sub.add_parser("index-plans", parents=[parent]).set_defaults(func=cmd_index_plans)
    write_phase = sub.add_parser("write-phase", parents=[parent])
    write_phase.add_argument("--plan-id", required=True)
    write_phase.add_argument("--phase-id", required=True)
    write_phase.add_argument("--title", required=True)
    write_phase.add_argument("--content-file", required=True)
    write_phase.add_argument("--status", default="Planned")
    write_phase.set_defaults(func=cmd_write_phase)
    write_task = sub.add_parser("write-task", parents=[parent])
    write_task.add_argument("--plan-id", required=True)
    write_task.add_argument("--phase-id", required=True)
    write_task.add_argument("--task-id", required=True)
    write_task.add_argument("--title", required=True)
    write_task.add_argument("--content-file", required=True)
    write_task.add_argument("--status", default="Planned")
    write_task.set_defaults(func=cmd_write_task)
    write_handoff = sub.add_parser("write-handoff", parents=[parent])
    write_handoff.add_argument("--type", required=True)
    write_handoff.add_argument("--title", required=True)
    write_handoff.add_argument("--content-file", required=True)
    write_handoff.add_argument("--related-spec")
    write_handoff.add_argument("--related-plan")
    write_handoff.add_argument("--related-phase")
    write_handoff.add_argument("--related-task")
    write_handoff.add_argument("--status", default="active")
    write_handoff.add_argument("--id")
    write_handoff.set_defaults(func=cmd_write_handoff)
    list_handoffs = sub.add_parser("list-handoffs", parents=[parent])
    list_handoffs.add_argument("--type", choices=sorted(HANDOFF_TYPES))
    list_handoffs.add_argument("--status")
    list_handoffs.set_defaults(func=cmd_list_handoffs)
    set_handoff = sub.add_parser("set-handoff-status", parents=[parent])
    set_handoff.add_argument("--id", required=True)
    set_handoff.add_argument("--status", required=True)
    set_handoff.set_defaults(func=cmd_set_handoff_status)
    sub.add_parser("index-handoffs", parents=[parent]).set_defaults(func=cmd_index_handoffs)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
