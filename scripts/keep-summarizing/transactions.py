"""One declared record effect; Markdown authority precedes disposable projections.

Requests contain effect, kind, knowledge-relative path, expected_digest (null for
create, sha256:<hex> otherwise), complete record front matter, and body. No agent
reasoning or acceptance fields are inputs. Semantic decisions remain with callers.
"""

from __future__ import annotations

import tempfile
from urllib.parse import urlsplit

from core import *
from indexes import open_question_files, rebuild_indexes, v3_note_issues

EFFECTS = {"create", "update", "transition", "supersede", "deprecate", "resolve-open-question"}
REQUEST_FIELDS = {"effect", "kind", "path", "expected_digest", "record", "body"}
NOTE_FIELDS = {
    "id", "title", "lifecycle_stage", "perspective", "status", "source_type", "summary",
    "tags", "created_at", "updated_at", "evidence", "related_notes", "supersedes",
    "superseded_by", "owner", "visibility", "sensitivity", "embedding",
}
QUESTION_FIELDS = {
    "id", "title", "perspective", "status", "created_at", "updated_at", "source_note_ids",
    "trigger_terms", "resolved_at", "resolved_by_note_id", "resolution_summary",
}


class KnowledgeError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise KnowledgeError(code, message)


def content_digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def record_path(root: Path, kind: str, relative: object, record: dict) -> Path:
    require(isinstance(relative, str), "KS_INVALID_PATH", "path must be knowledge-relative")
    rel = Path(relative)
    category = "notes" if kind == "note" else "open-questions"
    require(
        not rel.is_absolute() and ".." not in rel.parts and rel.as_posix() == relative
        and rel.parent.as_posix() == f"{category}/{record.get('perspective')}"
        and rel.suffix == ".md" and rel.name != "index.md"
        and re.fullmatch(r"[a-z0-9][a-z0-9._-]*\.md", rel.name) is not None,
        "KS_INVALID_PATH", "path must name one canonical record in its leaf perspective",
    )
    path = root / rel
    require(is_relative_to(path, root) and not any(parent.is_symlink() for parent in [path, *path.parents] if parent != root),
            "KS_INVALID_PATH", "canonical path must not traverse symlinks")
    return path


def validate_record(root: Path, path: Path, kind: str, record: dict, body: str) -> None:
    fields = NOTE_FIELDS if kind == "note" else QUESTION_FIELDS
    require(fields <= record.keys() and set(record) <= fields | ({"source"} if kind == "note" else set()),
            "KS_INVALID_RECORD", "complete contract front matter is required; unknown fields are not accepted")
    for key in ("id", "title", "perspective", "status", "created_at", "updated_at"):
        require(isinstance(record[key], str) and bool(record[key].strip()), "KS_INVALID_RECORD", f"{key} must be a nonempty string")
    require(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", record["id"]) is not None,
            "KS_INVALID_RECORD", "id must be a stable identifier")
    for key in ("created_at", "updated_at"):
        try:
            dt.date.fromisoformat(record[key])
        except ValueError as exc:
            raise KnowledgeError("KS_INVALID_RECORD", f"{key} must be an ISO date") from exc
    require(record["updated_at"] >= record["created_at"], "KS_INVALID_RECORD", "updated_at must not precede created_at")
    try:
        validate_leaf_perspective(record["perspective"])
    except SystemExit as exc:
        raise KnowledgeError("KS_INVALID_RECORD", str(exc)) from exc
    require(isinstance(body, str) and bool(body.strip()), "KS_INVALID_RECORD", "body must be nonempty Markdown")
    list_fields = ("tags", "related_notes", "supersedes", "superseded_by") if kind == "note" else ("source_note_ids", "trigger_terms")
    for key in list_fields:
        require(isinstance(record[key], list) and all(isinstance(item, str) and item.strip() for item in record[key]),
                "KS_INVALID_RECORD", f"{key} must be a list of strings")
    if kind == "note":
        require(not v3_note_issues(root, path, record), "KS_INVALID_RECORD", "; ".join(v3_note_issues(root, path, record)))
        require(record["status"] in project_config(root)["statuses"], "KS_INVALID_RECORD", "status is outside project configuration")
        require(record["owner"] == "keep-summarizing" and record["visibility"] == "private"
                and isinstance(record["sensitivity"], str) and record["sensitivity"] in DEFAULT_SENSITIVITIES,
                "KS_INVALID_RECORD", "invalid owner, visibility, or sensitivity")
        require(isinstance(record["summary"], str), "KS_INVALID_RECORD", "summary must be a string")
        embedding = record["embedding"]
        require(isinstance(embedding, dict) and set(embedding) == {"include", "chunk_strategy"}
                and isinstance(embedding["include"], bool) and embedding["chunk_strategy"] == "heading",
                "KS_INVALID_RECORD", "embedding must use the heading contract")
        require(isinstance(record["evidence"], list), "KS_INVALID_RECORD", "evidence must be a list")
        for evidence in record["evidence"]:
            require(isinstance(evidence, dict) and set(evidence) == {"type", "path", "relation"}
                    and isinstance(evidence["type"], str) and isinstance(evidence["relation"], str)
                    and evidence["type"] in EVIDENCE_TYPES and evidence["relation"] in EVIDENCE_RELATIONS
                    and isinstance(evidence["path"], str), "KS_INVALID_RECORD", "invalid evidence entry")
        if "source" in record:
            source = record["source"]
            require(isinstance(source, dict) and set(source) == {"type", "refs"}
                    and source["type"] == "curated" and isinstance(source["refs"], list)
                    and all(isinstance(ref, str) for ref in source["refs"]),
                    "KS_INVALID_RECORD", "source must use the curated source/ref contract")
        if record["status"] == "confirmed":
            require(bool(record["evidence"]), "KS_INVALID_RECORD", "confirmed note requires front matter evidence")
    else:
        require(bool(record["trigger_terms"]), "KS_INVALID_RECORD", "trigger_terms must be a nonempty list of nonempty strings")
        require(record["status"] in QUESTION_STATUSES, "KS_INVALID_RECORD", "invalid open-question status")
        for key in ("resolved_at", "resolved_by_note_id", "resolution_summary"):
            require(record[key] is None or isinstance(record[key], str), "KS_INVALID_RECORD", f"{key} must be a string or null")
        if record["status"] == "resolved":
            require(bool(record["resolved_at"]) and bool(record["resolution_summary"]),
                    "KS_INVALID_RECORD", "resolved question requires a date and resolution summary")
            try:
                dt.date.fromisoformat(record["resolved_at"])
            except ValueError as exc:
                raise KnowledgeError("KS_INVALID_RECORD", "resolved_at must be an ISO date") from exc


def canonical_catalog(root: Path) -> dict[str, list[Path]]:
    catalog: dict[str, list[Path]] = {}
    paths = sorted((root / "notes").glob("**/*.md")) + open_question_files(root)
    for path in paths:
        require(is_relative_to(path, root) and not path.is_symlink(), "KS_INVALID_PATH", "record candidate escapes canonical store")
        record, _ = read_front_matter(path)
        if isinstance(record.get("id"), str):
            catalog.setdefault(record["id"], []).append(path)
    return catalog


def validate_links(root: Path, path: Path, kind: str, record: dict, body: str, catalog: dict) -> None:
    def note_reference(value: str) -> None:
        matches = catalog.get(value, [])
        if not matches and value.startswith("notes/"):
            candidate = root / value
            if ".." not in Path(value).parts and is_relative_to(candidate, root) and candidate.is_file():
                linked, _ = read_front_matter(candidate)
                matches = catalog.get(linked.get("id"), [])
                require(matches == [candidate], "KS_INVALID_LINK", f"noncanonical note reference: {value}")
        require(len(matches) == 1 and matches[0] != path
                and matches[0].relative_to(root).parts[0] == "notes",
                "KS_INVALID_LINK", f"missing, ambiguous, or self note reference: {value}")

    keys = ("related_notes", "supersedes", "superseded_by") if kind == "note" else ("source_note_ids",)
    for key in keys:
        for value in record[key]:
            note_reference(value)
    if kind == "open-question" and record["resolved_by_note_id"]:
        note_reference(record["resolved_by_note_id"])
    if kind == "note":
        evidence_root = root.parent.parent if root.name == "knowledge" and root.parent.name == ".work-bundle" else root
        for evidence in record["evidence"]:
            rel = Path(evidence["path"])
            require(not rel.is_absolute() and ".." not in rel.parts and "credentials" not in rel.parts,
                    "KS_INVALID_LINK", "evidence must be a non-protected workspace-relative path")
            target = evidence_root / rel
            require(is_relative_to(target, evidence_root) and target.is_file(), "KS_INVALID_LINK", f"missing evidence path: {rel}")
    for target in re.findall(r"\[[^\]]+\]\(([^)#]*)(?:#[^)]+)?\)", body):
        if not target or urlsplit(target).scheme or target.startswith("?"):
            continue
        target = target.removeprefix("<").removesuffix(">")
        linked = path.parent / target
        require(is_relative_to(linked, root) and (linked.resolve() == path.resolve() or linked.is_file()),
                "KS_INVALID_LINK", f"broken or escaping Markdown link: {target}")


def validate_effect(effect: str, kind: str, old: dict | None, record: dict) -> None:
    status = record["status"]
    if effect == "create":
        require((kind == "note" and status not in {"superseded", "deprecated"})
                or (kind == "open-question" and status == "open"), "KS_INVALID_TRANSITION", "invalid initial state")
        return
    require(old is not None and isinstance(old.get("status"), str)
            and old["status"] in (DEFAULT_STATUSES if kind == "note" else QUESTION_STATUSES),
            "KS_INVALID_TRANSITION", "current canonical state is invalid")
    for key in ("id", "created_at", "perspective"):
        require(old.get(key) == record[key], "KS_IDENTITY_CONFLICT", f"{key} is immutable in a one-record replacement")
    old_status = old["status"]
    valid = (
        (effect == "update" and status == old_status)
        or (effect == "transition" and kind == "note" and status != old_status and status not in {"superseded", "deprecated"})
        or (effect == "supersede" and kind == "note" and status == "superseded" and old_status != status)
        or (effect == "deprecate" and kind == "note" and status == "deprecated" and old_status != status)
        or (effect == "resolve-open-question" and kind == "open-question" and old_status == "open" and status == "resolved")
    )
    require(valid, "KS_INVALID_TRANSITION", "effect does not match the current and target state")
    if kind == "note":
        if status != old_status and status in AUTHORITY_STATUSES:
            require(bool(record["evidence"]), "KS_INVALID_TRANSITION", "promotion requires front matter evidence")
        if effect in {"supersede", "deprecate"}:
            require(bool(record["superseded_by"]), "KS_INVALID_LINK", "replacement reference is required")


def rebuild_projections(root: Path, project: str) -> dict:
    return rebuild_indexes(root, project)


def mutate_record(root: Path, project: str, request: dict, *, dry_run: bool = False) -> dict:
    root = root.resolve()
    require(isinstance(request, dict) and set(request) == REQUEST_FIELDS,
            "KS_INVALID_REQUEST", "request must contain only effect, kind, path, expected_digest, record, body")
    effect, kind, record, body = (request[key] for key in ("effect", "kind", "record", "body"))
    require(isinstance(effect, str) and effect in EFFECTS and isinstance(kind, str) and kind in {"note", "open-question"}
            and isinstance(record, dict), "KS_INVALID_REQUEST", "invalid effect, kind, or record")
    path = record_path(root, kind, request["path"], record)
    old_bytes = path.read_bytes() if path.is_file() else None
    old = parse_front_matter(old_bytes.decode("utf-8"))[0] if old_bytes is not None else None
    if effect == "create":
        require(request["expected_digest"] is None and not path.exists(), "KS_COLLISION", "create requires an absent path and null digest")
    else:
        require(old_bytes is not None, "KS_RECORD_NOT_FOUND", "canonical record does not exist")
        require(request["expected_digest"] == content_digest(old_bytes), "KS_STALE_DIGEST", "expected digest differs from canonical bytes")
    validate_record(root, path, kind, record, body)
    validate_effect(effect, kind, old, record)
    catalog = canonical_catalog(root)
    require(not any(candidate != path for candidate in catalog.get(record["id"], [])), "KS_COLLISION", "record id already exists at another path")
    validate_links(root, path, kind, record, body, catalog)
    try:
        rendered = "---\n" + yaml.safe_dump(record, sort_keys=False, allow_unicode=True) + "---\n" + body
        require(parse_front_matter(rendered) == (record, body), "KS_INVALID_RECORD", "rendered record does not round-trip")
    except (yaml.YAMLError, TypeError, ValueError) as exc:
        raise KnowledgeError("KS_INVALID_RECORD", "record cannot be serialized losslessly") from exc
    result = {
        "effect": effect, "kind": kind, "path": request["path"], "id": record["id"],
        "old_status": old.get("status") if old else None, "status": record["status"],
        "digest": content_digest(rendered.encode("utf-8")),
        "canonical_status": "unchanged", "projection_status": "not-run", "dry_run": dry_run,
    }
    if dry_run:
        return result
    path.parent.mkdir(parents=True, exist_ok=True)
    sibling = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as staged:
            sibling = Path(staged.name)
            staged.write(rendered)
            staged.flush()
            os.fsync(staged.fileno())
        require(read_front_matter(sibling) == (record, body), "KS_INVALID_RECORD", "staged sibling does not round-trip")
        current = path.read_bytes() if path.is_file() else None
        require(current == old_bytes and (old_bytes is not None or not path.exists()),
                "KS_STALE_DIGEST", "canonical bytes changed while staging")
        os.replace(sibling, path)
        result["canonical_status"] = "replaced"
    except OSError as exc:
        raise KnowledgeError("KS_WRITE_FAILED", str(exc)) from exc
    finally:
        if sibling is not None:
            sibling.unlink(missing_ok=True)
    try:
        projections = rebuild_projections(root, project)
        result["projections"] = projections
        vector = projections.get("vector_status", {})
        if vector.get("status") != "rebuilt":
            raise RuntimeError(vector.get("reason") or "vector projection was not rebuilt")
        result["projection_status"] = "rebuilt"
    except Exception as exc:
        result.update(projection_status="stale", code="KS_PROJECTION_STALE", projection_error=str(exc),
                      rebuild_command=["scripts/ks.py", "index", "--project", project, "--knowledge-root", str(root)])
    return result


def cmd_mutate_knowledge(args: argparse.Namespace, *, kind: str | None = None, effects: set[str] | None = None) -> None:
    try:
        request = yaml.load(Path(args.request_file).read_text(encoding="utf-8"), Loader=KnowledgeLoader)
        require(isinstance(request, dict), "KS_INVALID_REQUEST", "request must be a mapping")
        require(kind is None or request.get("kind") == kind, "KS_INVALID_REQUEST", "command does not own this record kind")
        require(effects is None or (isinstance(request.get("effect"), str) and request["effect"] in effects),
                "KS_INVALID_REQUEST", "command does not own this effect")
        result = mutate_record(project_dir(args.project, args), args.project, request, dry_run=args.dry_run)
    except (KnowledgeError, yaml.YAMLError, ValueError, OSError) as exc:
        print(json.dumps({"code": getattr(exc, "code", "KS_INVALID_REQUEST"), "error": str(exc), "canonical_status": "unchanged"}, ensure_ascii=False))
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False))
    if result["projection_status"] == "stale":
        raise SystemExit(1)
