from core import *
from indexes import cmd_index

def cmd_write_note(args: argparse.Namespace) -> None:
    validate_leaf_perspective(args.perspective)
    root = project_dir(args.project, args)
    config = project_config(root)
    content = Path(args.content_file).read_text(encoding="utf-8")
    title_slug = slugify(args.title)
    path = root / "notes" / args.perspective / f"{title_slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not content.startswith("---\n"):
        nid = note_id(args.perspective, args.title)
        lifecycle_stage = args.lifecycle_stage or lifecycle_from_perspective(args.perspective)
        source_type = args.source_type or "discussion"
        content = f"""---
id: {nid}
title: {args.title}
lifecycle_stage: {lifecycle_stage}
perspective: {args.perspective}
status: draft
source_type: {source_type}
summary: ""
owner: keep-summarizing
created_at: {now_date()}
updated_at: {now_date()}
visibility: private
sensitivity: {config["default_sensitivity"]}
tags: []
evidence: []
related_notes: []
supersedes: []
superseded_by: []
embedding:
  include: true
  chunk_strategy: heading
---

# {args.title}

{content.rstrip()}
"""
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    cmd_index(args)
    print(str(path))



def cmd_output(args: argparse.Namespace) -> None:
    raise SystemExit("The reader-facing output directive moved to orchestrator create-document. Use orchestrator to write under .work-bundle/orchestration/docs/.")


def source_points(text: str) -> list[dict[str, str]]:
    points: list[dict[str, str]] = []
    headings: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if not pending:
            return
        excerpt = " ".join(item.strip() for item in pending if item.strip())
        pending.clear()
        if excerpt:
            points.append(
                {
                    "heading": " > ".join(headings) if headings else "(root)",
                    "excerpt": excerpt,
                }
            )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush()
            level = len(heading.group(1))
            headings = headings[: level - 1]
            headings.append(heading.group(2).strip())
            continue
        if not line:
            flush()
            continue
        if re.match(r"^([-*+]|\d+[.)])\s+", line):
            flush()
            points.append(
                {
                    "heading": " > ".join(headings) if headings else "(root)",
                    "excerpt": re.sub(r"^([-*+]|\d+[.)])\s+", "", line),
                }
            )
            continue
        pending.append(line)
    flush()
    return points


def cmd_breakdown_design(args: argparse.Namespace) -> None:
    text = Path(args.input).read_text(encoding="utf-8")
    default_parts = "development-design/architecture/decisions,development-design/workflow/data-flow,development-design/workflow/process-flow,development-design/architecture/patterns"
    parts = [part.strip() for part in (args.parts or default_parts).split(",") if part.strip()]
    for part in parts:
        validate_leaf_perspective(part)
    points = source_points(text)
    if not points:
        raise SystemExit("No meaningful source points found.")
    print("Validated scaffold only. Agent semantic review is required before persistence.")
    print("")
    print("| point_order | source_heading | suggested_leaf_perspective | suggested_note_title | target_path | source_excerpt |")
    print("| --- | --- | --- | --- | --- | --- |")
    for index, point in enumerate(points, start=1):
        perspective = parts[(index - 1) % len(parts)]
        title = point["heading"] if point["heading"] != "(root)" else f"Source Point {index}"
        title = re.sub(r"\s+", " ", title).strip()
        note_title = f"{title} Point {index}"
        target = f"notes/{perspective}/{slugify(note_title)}.md"
        heading = point["heading"].replace("|", "\\|")
        escaped_title = note_title.replace("|", "\\|")
        excerpt = point["excerpt"].replace("|", "\\|")
        print(f"| {index} | {heading} | {perspective} | {escaped_title} | {target} | {excerpt} |")
    print("")
    print(f"Coverage: {len(points)} source points mapped to atomic note/update candidates.")

