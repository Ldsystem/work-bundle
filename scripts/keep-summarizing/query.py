from core import *
from indexes import cmd_index

def retrieval_role(row: dict[str, object], target: str) -> str:
    status = str(row.get("status", ""))
    lifecycle = str(row.get("lifecycle_stage", ""))
    if status in BLOCKED_STATUSES:
        return "blocked"
    if status in {"draft", "proposed"}:
        return "candidate"
    if target in {"implementation_plan", "execution"}:
        if lifecycle == "development_design" and status in AUTHORITY_STATUSES:
            return "authority"
        if lifecycle == "implementation" and status in {"implemented", "current"}:
            return "authority"
        return "background"
    if target == "implementation_spec":
        if lifecycle in {"development_design", "implementation"} and status in AUTHORITY_STATUSES:
            return "authority"
        return "background"
    if target in {"customer_spec", "bidding"}:
        if lifecycle in {"tender", "investigation", "customer_design", "bidding"} and status in {"confirmed", "current"}:
            return "authority"
        return "background"
    if target == "deployment":
        if lifecycle == "implementation" and status in {"implemented", "current"}:
            return "authority"
        if lifecycle == "deployment" and status in AUTHORITY_STATUSES:
            return "authority"
        return "background"
    if target == "operation":
        if lifecycle in {"deployment", "implementation"} and status in {"implemented", "current"}:
            return "authority"
        if lifecycle in {"go_live_delivery", "operation"} and status in AUTHORITY_STATUSES:
            return "authority"
        return "background"
    raise SystemExit(f"Unknown retrieval target: {target}")


def target_lifecycles(target: str, include_background: bool) -> set[str]:
    if target == "implementation_spec":
        values = {"development_design", "implementation"}
        return values | {"bidding", "customer_design", "investigation"} if include_background else values
    if target in {"implementation_plan", "execution"}:
        values = {"development_design", "implementation"}
        return values | {"tender", "investigation", "customer_design", "bidding", "deployment", "operation"} if include_background else values
    if target in {"customer_spec", "bidding"}:
        values = {"tender", "investigation", "customer_design", "bidding"}
        return values | {"development_design", "implementation", "deployment"} if include_background else values
    if target == "deployment":
        values = {"implementation", "deployment"}
        return values | {"tender", "investigation", "customer_design", "bidding", "development_design"} if include_background else values
    if target == "operation":
        values = {"deployment", "go_live_delivery", "operation", "implementation"}
        return values | {"development_design", "customer_design", "investigation"} if include_background else values
    raise SystemExit(f"Unknown retrieval target: {target}")


def discovery_lifecycles(target: str, include_background: bool) -> set[str]:
    target_scope = target_lifecycles(target, include_background=False)
    if include_background:
        return set(LIFECYCLE_PATH_SEGMENTS)
    return target_scope


def fts_literal_query(query: str) -> str:
    terms = [term.strip() for term in re.split(r"\s+", query or "") if term.strip()]
    if not terms:
        return '""'
    return " ".join('"' + term.replace('"', '""') + '"' for term in terms)


def cmd_query(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    db_path = root / "indexes" / "knowledge.sqlite"
    if not db_path.exists():
        cmd_index(args)
    lifecycles = sorted(discovery_lifecycles(args.target, args.include_background))
    placeholders = ",".join("?" for _ in lifecycles)
    sql = f"""
        SELECT n.*, bm25(knowledge_note_fts) AS rank
        FROM knowledge_note n
        JOIN knowledge_note_fts ON knowledge_note_fts.rowid = n.rowid
        WHERE knowledge_note_fts MATCH ?
          AND n.lifecycle_stage IN ({placeholders})
        ORDER BY rank
        LIMIT ?
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        for row in conn.execute(sql, [fts_literal_query(args.query), *lifecycles, args.limit]):
            result = dict(row)
            result["retrieval_role"] = retrieval_role(result, args.target)
            print(json.dumps(result, ensure_ascii=False))
    finally:
        conn.close()
