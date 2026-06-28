from core import *
from indexes import cmd_index


def fts_literal_query(query: str) -> str:
    terms = [term.strip() for term in re.split(r"\s+", query or "") if term.strip()]
    if not terms:
        return '""'
    return " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)


def query_anchors(query: str) -> list[str]:
    seen: set[str] = set()
    anchors: list[str] = []
    for term in re.split(r"\s+", query or ""):
        anchor = re.sub(r"^[^\w.-]+|[^\w.-]+$", "", term).strip().lower()
        if anchor and anchor not in seen:
            seen.add(anchor)
            anchors.append(anchor)
    return anchors


def vector_index_status(root: Path) -> dict[str, object]:
    path = root / "indexes" / VECTOR_INDEX_STATUS_FILE
    if not path.exists():
        return {"status": "unavailable", "reason": "missing vector index status", "fallback": "sqlite_fts"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "failed", "reason": "invalid vector index status", "fallback": "sqlite_fts"}


def candidate_record(row: sqlite3.Row, anchors: list[str], policy_hint: str | None, fusion_rank: int) -> dict[str, object]:
    result = dict(row)
    tags = result.get("tags", "[]")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = []
    return {
        "id": result.get("id", ""),
        "path": result.get("path", ""),
        "title": result.get("title", ""),
        "lifecycle_stage": result.get("lifecycle_stage", ""),
        "perspective": result.get("perspective", ""),
        "status": result.get("status", ""),
        "source_type": result.get("source_type", ""),
        "updated_at": result.get("updated_at", ""),
        "summary": result.get("summary", ""),
        "tags": tags if isinstance(tags, list) else [],
        "mechanical_sources": {
            "fts": True,
            "vector": False,
            "bfs": False,
        },
        "mechanical_scores": {
            "fts_rank": result.get("rank"),
            "vector_distance": None,
            "fusion_rank": fusion_rank,
            "bfs_depth": None,
        },
        "trace": {
            "query_anchors": anchors,
            "seed_candidate_id": None,
            "expansion_path": [],
        },
        "policy_hint": policy_hint,
    }


def cmd_query(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    db_path = root / "indexes" / "knowledge.sqlite"
    if not db_path.exists():
        cmd_index(args)
    policy_hint = getattr(args, "target", None)
    if policy_hint and policy_hint not in RETRIEVAL_POLICY_HINTS:
        raise SystemExit(f"Unknown retrieval policy hint: {policy_hint}")
    anchors = query_anchors(args.query)
    sql = f"""
        SELECT n.*, bm25(knowledge_note_fts) AS rank
        FROM knowledge_note n
        JOIN knowledge_note_fts ON knowledge_note_fts.rowid = n.rowid
        WHERE knowledge_note_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        vector_status = vector_index_status(root)
        print(
            json.dumps(
                {
                    "query_trace": {
                        "policy_hint": policy_hint,
                        "query_anchors": anchors,
                        "sources": {
                            "fts": "queried",
                            "vector": vector_status.get("status", "unavailable"),
                            "bfs": "not_configured",
                        },
                    }
                },
                ensure_ascii=False,
            )
        )
        for fusion_rank, row in enumerate(conn.execute(sql, [fts_literal_query(args.query), args.limit]), start=1):
            print(json.dumps(candidate_record(row, anchors, policy_hint, fusion_rank), ensure_ascii=False))
    finally:
        conn.close()
