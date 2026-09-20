"""Schema-owned current specification-family adapter."""
from __future__ import annotations

from core import *
from bounded_closure import require_orchestration_admission, resolve_working_workspace
from artifact_store import (
    atomic_write_bytes,
    canonical_artifact_path, family_policy, load_catalog, parse_markdown_artifact,
    read_artifact, rebuild_index, serialize_markdown_mapping, transition_artifact,
    write_artifact,
)

CATALOG_PATH = Path(__file__).resolve().parents[2] / "references/assets/orchestration/contract/artifact-family-catalog-v3.yaml"
FAMILY = "specification"
QUALIFICATION_STATUSES = {"draft", "verified", "superseded"}
QUALIFICATION_TRANSITIONS = {
    "draft": {"verified", "superseded"},
    "verified": {"draft", "superseded"},
    "superseded": set(),
}
STRUCTURAL_INPUT_FIELDS = {
    "artifact_type", "schema_version", "id", "title", "status", "date_created",
    "last_updated", "purpose", "component", "version",
}


def _anchors(args: argparse.Namespace) -> dict[str, Path]:
    return {"workspace_root": resolve_workspace_root(args)}


def _policy() -> dict[str, object]:
    return family_policy(load_catalog(CATALOG_PATH), FAMILY)


def _path(args: argparse.Namespace, identity: str, state: str) -> Path:
    return canonical_artifact_path(_policy(), _anchors(args), identity=identity, state=state)


def _located(args: argparse.Namespace, identity: str) -> tuple[str, Path]:
    candidates = [(state, _path(args, identity, state)) for state in ("active", "archived")]
    existing = [(state, path) for state, path in candidates if path.is_file()]
    if len(existing) > 1:
        raise SystemExit(f"Specification canonical identity collision: {identity}")
    if not existing:
        raise SystemExit(f"Specification not found at canonical location: {identity}")
    return existing[0]


def _row(args: argparse.Namespace, data: dict[str, object]) -> dict[str, object]:
    identity = str(data["id"])
    _state, path = _located(args, identity)
    return {
        "type": "spec", "id": identity, "title": data["title"],
        "status": data["status"], "path": rel(path, args),
        "purpose": data["purpose"], "component": data["component"],
        "created_at": data["date_created"], "updated_at": data["last_updated"],
    }


def index_specs(args: argparse.Namespace) -> list[dict[str, object]]:
    result = rebuild_index(CATALOG_PATH, FAMILY, _anchors(args))
    raw_rows = [json.loads(line) for line in Path(str(result["path"])).read_text(encoding="utf-8").splitlines() if line.strip()]
    return [_row(args, row) for row in raw_rows]


def cmd_index_specs(args: argparse.Namespace) -> None:
    print(f"indexed {len(index_specs(args))} specs")


def _semantic_input(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    data, body = parse_markdown_artifact(text, source=str(path))
    overrides = sorted(STRUCTURAL_INPUT_FIELDS.intersection(data))
    if overrides:
        raise SystemExit("Specification semantic input contains structural field override: " + ", ".join(overrides))
    return data, body


def _next_identity(args: argparse.Namespace) -> str:
    date = now_date().replace("-", "")
    existing = list((orchestration_root(args) / "spec").glob(f"*/spec-{date}-*.spec.md"))
    return f"spec-{date}-{len(existing) + 1:03d}"


def cmd_write_spec(args: argparse.Namespace) -> None:
    authority = resolve_working_workspace(resolve_workspace_root(args))
    if authority is not None:
        require_orchestration_admission(authority, operation="ordinary_new", flow_id=args.id)
    if getattr(args, "filename", None):
        raise SystemExit("Specification filename override is not supported by the canonical family")
    if args.status not in QUALIFICATION_STATUSES:
        raise SystemExit(f"Invalid spec qualification status: {args.status}")
    identity = args.id or _next_identity(args)
    semantic, body = _semantic_input(Path(args.content_file))
    active_path = _path(args, identity, "active")
    archived_path = _path(args, identity, "archived")
    if archived_path.exists():
        raise SystemExit(f"Specification canonical identity collision: {identity}")
    existing = (
        read_artifact(CATALOG_PATH, FAMILY, _anchors(args), identity=identity, state="active")
        if active_path.exists()
        else None
    )
    if existing is not None and args.status != "draft":
        raise SystemExit("Specification content updates must return the specification to draft")
    if existing is not None and existing["data"].get("status") == "superseded":
        raise SystemExit("Superseded specification content cannot be changed")
    today = now_date()
    data = {
        **semantic, "artifact_type": FAMILY, "schema_version": 1, "id": identity,
        "title": args.title, "status": args.status,
        "date_created": str(existing["data"]["date_created"]) if existing else today,
        "last_updated": today, "purpose": args.purpose, "component": args.component,
        "version": args.version,
    }
    result = write_artifact(CATALOG_PATH, FAMILY, _anchors(args), data, state="active", body=body)
    print(rel(Path(str(result["path"])), args))


def cmd_list_specs(args: argparse.Namespace) -> None:
    for row in index_specs(args):
        if args.status and row.get("status") != args.status:
            continue
        print(json.dumps(row, ensure_ascii=False))


def replace_front_matter_value(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"Missing front matter: {path}")
    data, body = parse_markdown_artifact(text, source=str(path))
    data[key] = value
    for timestamp in ("last_updated", "updated_at"):
        if timestamp in data:
            data[timestamp] = now_date()
    atomic_write_bytes(path, serialize_markdown_mapping(data, body))


def _rebuild_after_transition(args: argparse.Namespace, identity: str) -> None:
    try:
        rebuild_index(CATALOG_PATH, FAMILY, _anchors(args))
    except (OSError, SystemExit) as exc:
        raise SystemExit(
            f"Specification {identity} moved but index rebuild failed (partial effect): {exc}"
        ) from exc


def cmd_set_spec_status(args: argparse.Namespace) -> None:
    if args.status == "archived":
        state, _current_path = _located(args, args.id)
        if state == "archived":
            print(args.id)
            return
        transition_artifact(CATALOG_PATH, FAMILY, _anchors(args), identity=args.id, current_state="active", target_state="archived")
        _rebuild_after_transition(args, args.id)
        print(args.id)
        return
    if args.status not in QUALIFICATION_STATUSES:
        raise SystemExit(f"Invalid spec qualification status: {args.status}")
    state, _current_path = _located(args, args.id)
    if state != "active":
        raise SystemExit("Archived specification qualification cannot be changed")
    current = read_artifact(CATALOG_PATH, FAMILY, _anchors(args), identity=args.id, state="active")
    data = dict(current["data"])
    if data["status"] == args.status:
        print(args.id)
        return
    if args.status not in QUALIFICATION_TRANSITIONS.get(str(data["status"]), set()):
        raise SystemExit(
            f"Invalid specification qualification transition: {data['status']} -> {args.status}"
        )
    data["status"] = args.status
    data["last_updated"] = now_date()
    write_artifact(CATALOG_PATH, FAMILY, _anchors(args), data, state="active", body=str(current["body"]))
    print(args.id)


def archive_spec_for_forced_finalization(args: argparse.Namespace, spec_id: str) -> Path:
    state, path = _located(args, spec_id)
    if state == "archived":
        return path
    result = transition_artifact(CATALOG_PATH, FAMILY, _anchors(args), identity=spec_id, current_state="active", target_state="archived")
    _rebuild_after_transition(args, spec_id)
    return Path(str(result["path"]))
