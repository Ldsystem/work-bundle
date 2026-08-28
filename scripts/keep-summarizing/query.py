from core import *
from indexes import (
    cmd_index,
    expected_vector_metadata,
    load_sqlite_vec,
    local_text_vector,
)


RRF_K = 60
MAX_VECTOR_DISTANCE = 1.0


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


def vector_compatibility(status: dict[str, object]) -> tuple[str, str | None]:
    state = str(status.get("status", "unavailable"))
    if state != "rebuilt":
        return state if state in {"unavailable", "failed"} else "unavailable", str(
            status.get("reason") or "vector index is not rebuilt"
        )
    expected = expected_vector_metadata()
    mismatches = [
        key
        for key in (
            "embedding_model",
            "embedding_model_version",
            "embedding_package",
            "embedding_package_version",
            "dimensions",
            "chunking",
            "index_schema",
        )
        if status.get(key) != expected[key]
    ]
    if mismatches:
        return "failed", f"vector index requires rebuild: incompatible {', '.join(mismatches)}"
    return "rebuilt", None


def candidate_record(
    row: sqlite3.Row | dict[str, object],
    anchors: list[str],
    policy_hint: str | None,
    fusion_rank: int,
    *,
    from_fts: bool,
    from_vector: bool,
) -> dict[str, object]:
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
            "fts": from_fts,
            "vector": from_vector,
            "bfs": False,
        },
        "mechanical_scores": {
            "fts_rank": result.get("rank") if from_fts else None,
            "vector_distance": result.get("vector_distance") if from_vector else None,
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


def reciprocal_rank_fusion(
    fts_rows: list[sqlite3.Row | dict[str, object]],
    vector_rows: list[sqlite3.Row | dict[str, object]],
    limit: int,
) -> list[tuple[dict[str, object], bool, bool]]:
    merged: dict[str, dict[str, object]] = {}
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    sources: dict[str, set[str]] = {}
    for source, rows in (("fts", fts_rows), ("vector", vector_rows)):
        for rank, row in enumerate(rows, start=1):
            record = dict(row)
            candidate_id = str(record.get("id") or record.get("document_id") or "")
            if not candidate_id:
                continue
            merged.setdefault(candidate_id, record)
            if source == "vector":
                merged[candidate_id]["vector_distance"] = record.get("vector_distance")
            elif merged[candidate_id].get("rank") is None:
                merged[candidate_id]["rank"] = record.get("rank")
            scores[candidate_id] = scores.get(candidate_id, 0.0) + 1.0 / (RRF_K + rank)
            best_rank[candidate_id] = min(best_rank.get(candidate_id, rank), rank)
            sources.setdefault(candidate_id, set()).add(source)
    ordered = sorted(merged, key=lambda item: (-scores[item], best_rank[item], item))[:limit]
    return [
        (merged[item], "fts" in sources[item], "vector" in sources[item])
        for item in ordered
    ]


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
        vector_state, vector_reason = vector_compatibility(vector_status)
        vector_rows: list[sqlite3.Row | dict[str, object]] = []
        if vector_state == "rebuilt":
            sqlite_vec, load_error = load_sqlite_vec(conn)
            if sqlite_vec is None:
                vector_state = "unavailable"
                vector_reason = load_error or "sqlite-vec unavailable"
            else:
                try:
                    query_vector = local_text_vector(args.query, query=True)
                    vector_sql = """
                        SELECT n.*, v.distance AS vector_distance
                        FROM knowledge_chunk_vec v
                        JOIN knowledge_note n ON n.id = v.document_id
                        WHERE v.embedding MATCH ? AND k = ?
                        ORDER BY v.distance
                    """
                    vector_rows = [
                        row
                        for row in conn.execute(
                            vector_sql,
                            [sqlite_vec.serialize_float32(query_vector), max(args.limit * 4, 20)],
                        )
                        if float(dict(row).get("vector_distance", float("inf"))) <= MAX_VECTOR_DISTANCE
                    ]
                    vector_state = "queried"
                except (ImportError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
                    vector_state = "failed"
                    vector_reason = f"vector query failed: {exc}"
                    vector_rows = []
        fts_rows = list(conn.execute(sql, [fts_literal_query(args.query), max(args.limit * 4, 20)]))
        trace = {
            "policy_hint": policy_hint,
            "query_anchors": anchors,
            "sources": {
                "fts": "queried",
                "vector": vector_state,
                "bfs": "not_configured",
            },
        }
        if vector_reason:
            trace["source_details"] = {"vector": {"reason": vector_reason}}
        print(
            json.dumps(
                {
                    "query_trace": trace
                },
                ensure_ascii=False,
            )
        )
        for fusion_rank, (row, from_fts, from_vector) in enumerate(
            reciprocal_rank_fusion(fts_rows, vector_rows, args.limit), start=1
        ):
            print(
                json.dumps(
                    candidate_record(
                        row,
                        anchors,
                        policy_hint,
                        fusion_rank,
                        from_fts=from_fts,
                        from_vector=from_vector,
                    ),
                    ensure_ascii=False,
                )
            )
    finally:
        conn.close()
