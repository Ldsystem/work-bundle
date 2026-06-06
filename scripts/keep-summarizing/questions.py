from core import *
from indexes import build_open_question_index

def cmd_add_question(args: argparse.Namespace) -> None:
    validate_leaf_perspective(args.perspective)
    root = project_dir(args.project, args)
    body = Path(args.content_file).read_text(encoding="utf-8").strip()
    qid = question_id(args.perspective, args.title)
    path = root / "open-questions" / args.perspective / f"{slugify(args.title)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    trigger_terms = csv_items(args.trigger_terms)
    source_note_ids = csv_items(args.source_note_ids)
    content = f"""---
id: {qid}
title: {args.title}
perspective: {args.perspective}
status: open
created_at: {now_date()}
updated_at: {now_date()}
{yaml_list_field("source_note_ids", source_note_ids)}
{yaml_list_field("trigger_terms", trigger_terms)}
resolved_at:
resolved_by_note_id:
resolution_summary:
---

# {args.title}

## Question

{body}

## Why It Matters

- Track only because the user provided or confirmed this as future work.

## Resolution

Unresolved.
"""
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    build_open_question_index(root, args.project)
    print(str(path))


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
    root = project_dir(args.project, args)
    rows = load_open_question_registry(root)
    matches = [row for row in rows if row.get("id") == args.id]
    if not matches:
        raise SystemExit(f"Open question not found: {args.id}")
    path = root / str(matches[0]["path"])
    fm, body = read_front_matter(path)
    resolution = Path(args.resolution_file).read_text(encoding="utf-8").strip()
    title = str(fm.get("title", args.id))
    perspective = str(fm.get("perspective", ""))
    trigger_terms = fm.get("trigger_terms", [])
    source_note_ids = fm.get("source_note_ids", [])
    clean_body = body.strip()
    clean_body = clean_body.split("\n## Resolved Answer\n", 1)[0].rstrip()
    clean_body = clean_body.replace("## Resolution\n\nUnresolved.", "## Resolution\n\nResolved. See resolved answer below.")
    new_content = f"""---
id: {args.id}
title: {title}
perspective: {perspective}
status: resolved
created_at: {fm.get("created_at", now_date())}
updated_at: {now_date()}
{yaml_list_field("source_note_ids", source_note_ids)}
{yaml_list_field("trigger_terms", trigger_terms)}
resolved_at: {now_date()}
resolved_by_note_id: {args.resolved_by_note or ""}
resolution_summary: {resolution.splitlines()[0] if resolution else ""}
---

{clean_body}

## Resolved Answer

{resolution}
"""
    path.write_text(new_content.rstrip() + "\n", encoding="utf-8")
    build_open_question_index(root, args.project)
    print(str(path))


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
