from core import *

from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version

VECTOR_DIMENSIONS = 384
SQLITE_VEC_PACKAGE = "sqlite-vec"
SQLITE_VEC_IMPORT = "sqlite_vec"
EMBEDDING_PACKAGE = "fastembed"
EMBEDDING_PACKAGE_VERSION = "0.8.0"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_MODEL_VERSION = "v1.5"
VECTOR_INDEX_SCHEMA = "knowledge-chunk-vec-v2"
VECTOR_CHUNKING = "document-body-v1"


def install_sqlite_vec() -> tuple[object | None, str | None]:
    try:
        return __import__(SQLITE_VEC_IMPORT), None
    except ImportError as exc:
        return None, f"sqlite-vec unavailable in the uv-managed environment: {exc}"


def sqlite_vec_availability_probe() -> dict[str, object]:
    """Probe import and extension loading independently from a production rebuild."""
    try:
        sqlite_vec = __import__(SQLITE_VEC_IMPORT)
    except ImportError:
        return {
            "status": "unavailable",
            "reason": "sqlite-vec probe unavailable: import failed",
        }
    conn = sqlite3.connect(":memory:")
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return {"status": "available", "reason": None}
    except Exception:
        return {
            "status": "unavailable",
            "reason": "sqlite-vec probe unavailable: temporary load failed",
        }
    finally:
        try:
            conn.enable_load_extension(False)
        except Exception:
            pass
        conn.close()


def load_sqlite_vec(conn: sqlite3.Connection) -> tuple[object | None, str | None]:
    sqlite_vec, error = install_sqlite_vec()
    if sqlite_vec is None:
        return None, error
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return sqlite_vec, None
    except Exception as exc:
        return None, f"sqlite-vec load failed: {exc}"
    finally:
        try:
            conn.enable_load_extension(False)
        except Exception:
            pass


@lru_cache(maxsize=1)
def embedding_model() -> object:
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=EMBEDDING_MODEL)


def embedding_backend_status() -> tuple[object | None, str | None]:
    try:
        installed_version = version(EMBEDDING_PACKAGE)
        if installed_version != EMBEDDING_PACKAGE_VERSION:
            return None, (
                f"FastEmbed version mismatch: expected {EMBEDDING_PACKAGE_VERSION}, "
                f"got {installed_version}"
            )
        return embedding_model(), None
    except (ImportError, OSError, RuntimeError, ValueError, PackageNotFoundError) as exc:
        return None, f"FastEmbed model unavailable in the uv-managed environment: {exc}"


def local_text_vector(text: str, *, query: bool = False) -> list[float]:
    model, error = embedding_backend_status()
    if model is None:
        raise RuntimeError(error or "FastEmbed model unavailable")
    embed = model.query_embed if query else model.passage_embed
    vector = list(next(iter(embed([text]))))
    if len(vector) != VECTOR_DIMENSIONS:
        raise RuntimeError(
            f"FastEmbed model dimension mismatch: expected {VECTOR_DIMENSIONS}, got {len(vector)}"
        )
    return [float(value) for value in vector]


def expected_vector_metadata() -> dict[str, object]:
    return {
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_version": EMBEDDING_MODEL_VERSION,
        "embedding_package": EMBEDDING_PACKAGE,
        "embedding_package_version": EMBEDDING_PACKAGE_VERSION,
        "dimensions": VECTOR_DIMENSIONS,
        "chunking": VECTOR_CHUNKING,
        "index_schema": VECTOR_INDEX_SCHEMA,
    }

def markdown_files(root: Path) -> list[Path]:
    candidates = list((root / "notes").glob("**/*.md")) + list((root / "context-packs").glob("*.md"))
    return sorted(path for path in candidates if path.is_file())


def open_question_files(root: Path) -> list[Path]:
    base = root / "open-questions"
    if not base.exists():
        return []
    return sorted(path for path in base.glob("**/*.md") if path.is_file() and path.name != "index.md")


def v3_note_issues(root: Path, path: Path, fm: dict[str, object]) -> list[str]:
    rel = path.relative_to(root).as_posix()
    issues: list[str] = []
    for key in ["id", "title", "lifecycle_stage", "perspective", "status", "source_type"]:
        if key not in fm:
            issues.append(f"missing {key}: {rel}")
    lifecycle_stage = str(fm.get("lifecycle_stage", ""))
    perspective = str(fm.get("perspective", ""))
    status = str(fm.get("status", ""))
    source_type = str(fm.get("source_type", ""))
    if lifecycle_stage and lifecycle_stage not in LIFECYCLE_PATH_SEGMENTS:
        issues.append(f"invalid lifecycle_stage {lifecycle_stage}: {rel}")
    if perspective and perspective not in V3_LEAF_PERSPECTIVES and perspective not in LEAF_PERSPECTIVES:
        issues.append(f"invalid perspective {perspective}: {rel}")
    if lifecycle_stage and perspective and perspective in V3_LEAF_PERSPECTIVES:
        expected_segment = lifecycle_to_path_segment(lifecycle_stage)
        if not perspective.startswith(f"{expected_segment}/"):
            issues.append(f"lifecycle/perspective mismatch: {rel}")
        if rel.startswith("notes/") and f"notes/{perspective}/" not in rel:
            issues.append(f"perspective/path mismatch: {rel}")
    if status and status not in DEFAULT_STATUSES:
        issues.append(f"invalid status {status}: {rel}")
    if source_type and source_type not in SOURCE_TYPES:
        issues.append(f"invalid source_type {source_type}: {rel}")
    if "truth_level" in fm:
        issues.append(f"forbidden truth_level: {rel}")
    if status == "implemented" and not has_frontmatter_list(fm, "evidence"):
        issues.append(f"missing evidence for implemented note: {rel}")
    return issues


def strip_non_retrieval_sections(body: str) -> str:
    lines = body.splitlines()
    kept: list[str] = []
    skip = False
    for line in lines:
        if re.match(r"^##\s+(Version History|Accepted Open Questions|Open Questions|Superseded Theory)\s*$", line, flags=re.IGNORECASE):
            skip = True
            continue
        if skip and line.startswith("## "):
            skip = False
        if not skip:
            kept.append(line)
    return "\n".join(kept).strip()


def build_sqlite_index(root: Path, docs: list[dict[str, object]]) -> None:
    db_path = root / "indexes" / "knowledge.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            DROP TABLE IF EXISTS knowledge_note_fts;
            DROP TABLE IF EXISTS knowledge_note_relation;
            DROP TABLE IF EXISTS knowledge_note;
            CREATE TABLE knowledge_note (
              rowid INTEGER PRIMARY KEY,
              id TEXT NOT NULL UNIQUE,
              path TEXT NOT NULL UNIQUE,
              title TEXT NOT NULL,
              lifecycle_stage TEXT NOT NULL,
              perspective TEXT NOT NULL,
              status TEXT NOT NULL,
              source_type TEXT NOT NULL,
              updated_at TEXT,
              summary TEXT,
              tags TEXT,
              body TEXT NOT NULL
            );
            CREATE TABLE knowledge_note_relation (
              note_id TEXT NOT NULL,
              related_note_id TEXT NOT NULL,
              relation_type TEXT NOT NULL,
              PRIMARY KEY (note_id, related_note_id, relation_type),
              FOREIGN KEY (note_id) REFERENCES knowledge_note(id) ON DELETE CASCADE
            );
            CREATE VIRTUAL TABLE knowledge_note_fts USING fts5(
              title,
              summary,
              body,
              tags,
              content='knowledge_note',
              content_rowid='rowid'
            );
            """
        )
        for doc in docs:
            if not doc.get("sqlite_include"):
                continue
            cursor = conn.execute(
                """
                INSERT INTO knowledge_note(id, path, title, lifecycle_stage, perspective, status, source_type, updated_at, summary, tags, body)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc["id"],
                    doc["path"],
                    doc["title"],
                    doc.get("lifecycle_stage", ""),
                    doc.get("perspective", ""),
                    doc.get("status", ""),
                    doc.get("source_type", ""),
                    doc.get("updated_at", ""),
                    doc.get("summary", ""),
                    json.dumps(doc.get("tags", []), ensure_ascii=False),
                    doc.get("body", ""),
                ),
            )
            conn.execute(
                "INSERT INTO knowledge_note_fts(rowid, title, summary, body, tags) VALUES (?, ?, ?, ?, ?)",
                (cursor.lastrowid, doc["title"], doc.get("summary", ""), doc.get("body", ""), json.dumps(doc.get("tags", []), ensure_ascii=False)),
            )
        conn.commit()
    finally:
        conn.close()


def build_vector_index_status(root: Path, chunks: list[dict[str, object]], project: str, *, install_missing: bool = True) -> dict[str, object]:
    indexes = root / "indexes"
    artifact_path = indexes / VECTOR_INDEX_ARTIFACT_FILE
    db_path = indexes / "knowledge.sqlite"
    base_status = {
        "generated_at": now_ts(),
        "project": project,
        "artifact": VECTOR_INDEX_ARTIFACT_FILE,
        "chunks_considered": len(chunks),
        "backend": "sqlite-vec",
    }

    if not install_missing:
        status = {
            **base_status,
            "status": "unavailable",
            "chunks_indexed": 0,
            "reason": "sqlite-vec install disabled",
            "fallback": "sqlite_fts",
        }
        artifact_path.write_text("", encoding="utf-8")
        (indexes / VECTOR_INDEX_STATUS_FILE).write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return status

    conn = sqlite3.connect(db_path)
    try:
        sqlite_vec, error = load_sqlite_vec(conn)
        if sqlite_vec is None:
            status = {
                **base_status,
                "status": "unavailable",
                "chunks_indexed": 0,
                "reason": error or "sqlite-vec unavailable",
                "fallback": "sqlite_fts",
            }
            artifact_path.write_text("", encoding="utf-8")
        else:
            model, model_error = embedding_backend_status()
            if model is None:
                status = {
                    **base_status,
                    "status": "unavailable",
                    "chunks_indexed": 0,
                    "reason": model_error or "FastEmbed model unavailable",
                    "fallback": "sqlite_fts",
                }
                artifact_path.write_text("", encoding="utf-8")
                (indexes / VECTOR_INDEX_STATUS_FILE).write_text(
                    json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                return status
            conn.execute("DROP TABLE IF EXISTS knowledge_chunk_vec")
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE knowledge_chunk_vec USING vec0(
                  chunk_id TEXT,
                  document_id TEXT,
                  path TEXT,
                  embedding FLOAT[{VECTOR_DIMENSIONS}]
                )
                """
            )
            rows: list[dict[str, object]] = []
            for chunk in chunks:
                note = conn.execute(
                    "SELECT title, summary, body, tags FROM knowledge_note WHERE id = ?",
                    [chunk["document_id"]],
                ).fetchone()
                source_text = " ".join(str(value or "") for value in (note or ()))
                embedding = local_text_vector(source_text)
                conn.execute(
                    "INSERT INTO knowledge_chunk_vec(chunk_id, document_id, path, embedding) VALUES (?, ?, ?, ?)",
                    (
                        chunk["chunk_id"],
                        chunk["document_id"],
                        chunk["path"],
                        sqlite_vec.serialize_float32(embedding),
                    ),
                )
                rows.append(
                    {
                        "chunk_id": chunk["chunk_id"],
                        "document_id": chunk["document_id"],
                        "path": chunk["path"],
                        "backend": "sqlite-vec",
                        "dimensions": VECTOR_DIMENSIONS,
                        "embedding_model": EMBEDDING_MODEL,
                    }
                )
            conn.commit()
            artifact_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + ("\n" if rows else ""),
                encoding="utf-8",
            )
            version = conn.execute("SELECT vec_version()").fetchone()[0]
            status = {
                **base_status,
                "status": "rebuilt",
                "chunks_indexed": len(rows),
                "extension": "sqlite-vec",
                "extension_version": version,
                "table": "knowledge_chunk_vec",
                **expected_vector_metadata(),
            }
    finally:
        conn.close()

    (indexes / VECTOR_INDEX_STATUS_FILE).write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status


def cmd_index(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    config = project_config(root)
    indexes = root / "indexes"
    indexes.mkdir(parents=True, exist_ok=True)
    docs = []
    chunks = []
    manifest = {
        "generated_at": now_ts(),
        "project": args.project,
        "documents": [],
    }
    for path in markdown_files(root):
        rel = path.relative_to(root).as_posix()
        fm, body = read_front_matter(path)
        if not fm:
            continue
        status = str(fm.get("status", "draft"))
        sensitivity = str(fm.get("sensitivity", "normal"))
        # Discovery is authority-neutral: lifecycle status is evaluated only after
        # retrieval, while sensitivity remains a legitimate indexing boundary.
        include = sensitivity not in config["exclude_sensitivity"]
        doc = {
            "id": fm.get("id", rel),
            "path": rel,
            "title": fm.get("title", path.stem),
            "lifecycle_stage": fm.get("lifecycle_stage", ""),
            "perspective": fm.get("perspective", ""),
            "status": status,
            "source_type": fm.get("source_type", ""),
            "summary": fm.get("summary", ""),
            "sensitivity": sensitivity,
            "include": include,
            "updated_at": fm.get("updated_at", ""),
            "tags": fm.get("tags", []),
            "body": strip_non_retrieval_sections(body),
            "sqlite_include": rel.startswith("notes/"),
        }
        docs.append(doc)
        if include:
            text_hash = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
            chunks.append(
                {
                    "chunk_id": f"{doc['id']}#body",
                    "document_id": doc["id"],
                    "path": rel,
                    "heading": "Body",
                    "text_hash": text_hash,
                    "tags": fm.get("tags", []),
                }
            )
            manifest["documents"].append({"id": doc["id"], "path": rel, "text_hash": text_hash})
    (indexes / "document-registry.jsonl").write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in docs) + ("\n" if docs else ""), encoding="utf-8")
    (indexes / "chunk-registry.jsonl").write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in chunks) + ("\n" if chunks else ""), encoding="utf-8")
    (indexes / "embedding-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (indexes / "backlink-map.json").write_text("{}\n", encoding="utf-8")
    build_sqlite_index(root, docs)
    vector_status = build_vector_index_status(root, chunks, args.project)
    open_questions = build_open_question_index(root, args.project)
    index_status = {
        "index_status": {
            "document_registry": "rebuilt",
            "chunk_registry": "rebuilt",
            "sqlite_fts": "rebuilt",
            "vector_index": vector_status["status"],
            "open_question_registry": "rebuilt",
            "blockers": [],
        },
        "counts": {
            "documents": len(docs),
            "chunks": len(chunks),
            "open_questions": len(open_questions),
        },
        "vector_status": vector_status,
    }
    print(json.dumps(index_status, ensure_ascii=False))


def build_open_question_index(root: Path, project: str) -> list[dict[str, object]]:
    indexes = root / "indexes"
    indexes.mkdir(parents=True, exist_ok=True)
    open_questions = root / "open-questions"
    open_questions.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    by_perspective: dict[str, list[dict[str, object]]] = {}
    for path in open_question_files(root):
        fm, _ = read_front_matter(path)
        if not fm:
            continue
        rel = path.relative_to(root).as_posix()
        status = str(fm.get("status", "open"))
        row = {
            "id": fm.get("id", rel),
            "title": fm.get("title", path.stem),
            "path": rel,
            "perspective": fm.get("perspective", ""),
            "status": status,
            "trigger_terms": fm.get("trigger_terms", []),
            "updated_at": fm.get("updated_at", ""),
            "resolved_by_note_id": fm.get("resolved_by_note_id", ""),
        }
        rows.append(row)
        by_perspective.setdefault(str(row["perspective"]), []).append(row)
    (indexes / "open-question-registry.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )
    index_lines = ["# Open Questions", "", "Generated from standalone open-question notes.", ""]
    for row in rows:
        index_lines.append(f"- [{row['status']}] {row['id']} - {row['title']} ({row['path']})")
    (open_questions / "index.md").write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")
    for perspective, items in by_perspective.items():
        if not perspective:
            continue
        perspective_dir = open_questions / perspective
        perspective_dir.mkdir(parents=True, exist_ok=True)
        lines = [f"# {perspective} Open Questions", "", "Generated from standalone open-question notes.", ""]
        for row in items:
            lines.append(f"- [{row['status']}] {row['id']} - {row['title']} ({row['path']})")
        (perspective_dir / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return rows


def cmd_index_open_questions(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    rows = build_open_question_index(root, args.project)
    print(f"indexed {len(rows)} open questions")
