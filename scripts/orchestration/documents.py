from core import *
from handoffs import list_executor_results
from plans import index_plans
from specs import index_specs

def cmd_write_doc(args: argparse.Namespace) -> None:
    content = Path(args.content_file).read_text(encoding="utf-8")
    target = orchestration_root(args) / "docs" / f"{slugify(args.title)}.md"
    write_text_safely(target, content, args)
    print(rel(target, args))


def cmd_state(args: argparse.Namespace) -> None:
    state = {
        "specs": count_by_status(index_specs(args)),
        "plans": count_by_status(index_plans(args)),
        "executor_results": count_by_status(
            list_executor_results(args), status_key="result_state"
        ),
        "docs": len(list((orchestration_root(args) / "docs").glob("*.md"))),
    }
    print(json.dumps(state, ensure_ascii=False))


def cmd_related(args: argparse.Namespace) -> None:
    rows = [*index_specs(args), *index_plans(args), *list_executor_results(args)]
    for row in rows:
        if args.id in json.dumps(row, ensure_ascii=False):
            print(json.dumps(row, ensure_ascii=False))


def cmd_next_action_candidates(args: argparse.Namespace) -> None:
    for row in list_executor_results(args):
        if row.get("artifact_type") == "executor-result" and row.get("result_state") == "active":
            print(json.dumps({"action": "review-executor-result", "executor_result_id": row.get("id"), "reason": "active executor result exists"}, ensure_ascii=False))
    for row in index_plans(args):
        if row.get("type") == "task" and row.get("status") == "planned":
            print(json.dumps({"action": "continue-task", "task_id": row.get("id"), "plan_id": row.get("plan_id"), "phase_id": row.get("phase_id"), "reason": "task is executable or in progress"}, ensure_ascii=False))


def cmd_git_status(args: argparse.Namespace) -> None:
    root = resolve_workspace_root(args)
    git = root / ".git"
    if not git.exists():
        print(json.dumps({"git": "absent", "project_root": str(root)}, ensure_ascii=False))
        return
    print(json.dumps({"git": "present", "project_root": str(root)}, ensure_ascii=False))
