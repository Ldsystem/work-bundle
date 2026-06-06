from core import *
from handoffs import index_handoffs
from plans import index_plans
from specs import index_specs, load_index

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

