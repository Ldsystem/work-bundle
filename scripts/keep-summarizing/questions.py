from core import *
from indexes import build_open_question_index
from transactions import cmd_mutate_knowledge

def cmd_add_question(args: argparse.Namespace) -> None:
    cmd_mutate_knowledge(args, kind="open-question", effects={"create"})


def load_open_question_registry(root: Path) -> list[dict[str, object]]:
    registry = root / "indexes" / "open-question-registry.jsonl"
    if not registry.exists():
        build_open_question_index(root, root.name)
    if not registry.exists():
        return []
    return [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_list_questions(args: argparse.Namespace) -> None:
    if args.status and args.status not in QUESTION_STATUSES:
        raise SystemExit(f"Invalid open-question status: {args.status}")
    if args.perspective and args.perspective not in ALL_PERSPECTIVES:
        raise SystemExit(f"Invalid perspective: {args.perspective}")
    root = project_dir(args.project, args)
    rows = load_open_question_registry(root)
    for row in rows:
        if args.status and row.get("status") != args.status:
            continue
        if args.perspective and row.get("perspective") != args.perspective:
            continue
        print(json.dumps(row, ensure_ascii=False))


def cmd_resolve_question(args: argparse.Namespace) -> None:
    cmd_mutate_knowledge(args, kind="open-question", effects={"resolve-open-question"})


def cmd_match_questions(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    if args.text_file:
        haystack = Path(args.text_file).read_text(encoding="utf-8")
    else:
        haystack = args.text or ""
    haystack_lower = haystack.lower()
    rows = load_open_question_registry(root)
    matches = []
    for row in rows:
        if row.get("status") != "open" and not args.include_resolved:
            continue
        terms = row.get("trigger_terms", [])
        if not isinstance(terms, list):
            terms = []
        matched_terms = [term for term in terms if str(term).lower() in haystack_lower]
        if matched_terms:
            matched = dict(row)
            matched["matched_terms"] = matched_terms
            matches.append(matched)
    for row in matches:
        print(json.dumps(row, ensure_ascii=False))
