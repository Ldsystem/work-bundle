#!/usr/bin/env python3
"""Deterministic helpers for the orchestrator skill."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path


def _artifact_store_module():
    """Load the orchestration sibling even when this file is loaded directly."""
    module_path = Path(__file__).with_name("artifact_store.py").resolve()
    existing = sys.modules.get("artifact_store")
    if existing is not None:
        if Path(str(getattr(existing, "__file__", ""))).resolve() != module_path:
            raise ImportError("artifact_store module collision")
        return existing
    spec = importlib.util.spec_from_file_location("artifact_store", module_path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load orchestration artifact_store")
    module = importlib.util.module_from_spec(spec)
    sys.modules["artifact_store"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("artifact_store", None)
        raise
    return module


_artifact_store = _artifact_store_module()
atomic_write_bytes = _artifact_store.atomic_write_bytes
parse_markdown_artifact = _artifact_store.parse_markdown_artifact


def _infrastructure_module():
    """Load the shared infrastructure owner without making the hyphenated path a package."""
    module_path = Path(__file__).resolve().parents[1] / "work-bundle" / "infrastructure.py"
    existing = sys.modules.get("work_bundle_infrastructure")
    if existing is not None:
        if Path(str(getattr(existing, "__file__", ""))).resolve() != module_path:
            raise ImportError("work_bundle_infrastructure module collision")
        return existing
    spec = importlib.util.spec_from_file_location("work_bundle_infrastructure", module_path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load work-bundle infrastructure")
    module = importlib.util.module_from_spec(spec)
    sys.modules["work_bundle_infrastructure"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("work_bundle_infrastructure", None)
        raise
    return module


_infrastructure = _infrastructure_module()


SPEC_STATUSES = {"draft", "active", "verified", "implemented", "reviewed", "superseded", "archived"}
PLAN_STATUSES = {"Planned", "In progress", "Completed", "Deprecated", "On Hold"}
RETRIEVAL_ROLES = {"authority", "candidate", "background", "blocked"}
# Directive policies describe classification/output intent only. Knowledge
# discovery remains neutral and cross-stage before agent authority classification.
DIRECTIVE_POLICY_MAP = {
    "create-specification": "implementation_spec",
    "create-implementation-plan": "implementation_plan",
    "create-document": "customer_spec",
    "create-handoff": "implementation_plan",
    "review-plan": "implementation_plan",
    "execute-plan": "execution",
    "customer-spec": "customer_spec",
    "bidding": "bidding",
    "deployment": "deployment",
    "operation": "operation",
}


def now_date() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-") or "untitled"


def is_relative_to(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


def project_registry_path() -> Path:
    try:
        return _infrastructure.resolve_project_registry_path()
    except _infrastructure.InfrastructureError as exc:
        raise SystemExit(exc.code) from exc


def resolve_workspace_root(args: argparse.Namespace) -> Path:
    explicit_workspace = getattr(args, "workspace_root", None)
    explicit_project = getattr(args, "project_root", None)
    try:
        context = _infrastructure.resolve_anchor_context(
            workspace_root=Path(explicit_workspace) if explicit_workspace else None,
            project_root=Path(explicit_project) if explicit_project else None,
            cwd=Path.cwd(),
        )
    except _infrastructure.InfrastructureError as exc:
        raise SystemExit(exc.code) from exc
    return context.workspace_root


def _member_roots(root: Path) -> list[Path]:
    try:
        metadata = _infrastructure.load_workspace_metadata(root)
        registry = _infrastructure.load_project_registry()
        binding = _infrastructure.join_workspace_binding(metadata, registry, expected_workspace_root=root)
    except _infrastructure.InfrastructureError:
        return []
    repositories = binding.get("repositories")
    if not isinstance(repositories, dict):
        return []
    return [
        Path(str(item["project_root"])).expanduser().resolve()
        for item in repositories.values()
        if isinstance(item, dict) and item.get("project_root")
    ]


def resolve_member_project_root(args: argparse.Namespace, workspace: Path | None = None) -> Path:
    explicit_workspace = workspace or getattr(args, "workspace_root", None)
    explicit_project = getattr(args, "project_root", None)
    try:
        context = _infrastructure.resolve_anchor_context(
            workspace_root=Path(explicit_workspace) if explicit_workspace else None,
            project_root=Path(explicit_project) if explicit_project else None,
            cwd=Path.cwd(),
            member_required=True,
        )
    except _infrastructure.InfrastructureError as exc:
        raise SystemExit(exc.code) from exc
    if context.project_root is None:
        raise SystemExit("WB_PROJECT_ROOT_AMBIGUOUS")
    return context.project_root


def work_bundle(args: argparse.Namespace) -> Path:
    return resolve_workspace_root(args) / ".work-bundle"


def orchestration_root(args: argparse.Namespace) -> Path:
    return work_bundle(args) / "orchestration"


def resolve_execution_artifact_path(
    workspace_root: Path,
    *,
    execution_id: str,
    artifact_path: str,
    source_members: list[Path],
) -> Path:
    """Resolve run-owned output under the containing workspace, never a source member."""

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", execution_id):
        raise SystemExit("Execution artifact path requires a valid execution id")
    relative = Path(artifact_path)
    if (
        not artifact_path.strip()
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise SystemExit("Execution artifact path must be a canonical relative path")
    target = (
        workspace_root.expanduser().resolve()
        / "orchestration"
        / "executions"
        / execution_id
        / relative
    ).resolve()
    for source_member in source_members:
        if is_relative_to(target, source_member.expanduser().resolve()):
            raise SystemExit("Execution artifact path resolves inside a source member")
    return target


def ensure_under_orchestration(path: Path, args: argparse.Namespace) -> Path:
    resolved = path.resolve()
    allowed = orchestration_root(args).resolve()
    if not is_relative_to(resolved, allowed):
        raise SystemExit(f"Path escapes orchestration root: {resolved}")
    if ".work-bundle/knowledge" in resolved.as_posix():
        raise SystemExit(f"Orchestrator must not write durable knowledge: {resolved}")
    return resolved


def read_front_matter(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    data, body = parse_markdown_artifact(text, source=str(path))
    return data, body


def write_text_safely(path: Path, content: str, args: argparse.Namespace) -> None:
    target = ensure_under_orchestration(path, args)
    atomic_write_bytes(target, (content.rstrip() + "\n").encode("utf-8"))


def sequence_id(root: Path, prefix: str) -> str:
    date = now_date().replace("-", "")
    existing = sorted(root.glob(f"**/{prefix}-{date}-*.md"))
    return f"{prefix}-{date}-{len(existing) + 1:03d}"


def ensure_front_matter(content: str, fields: dict[str, object]) -> str:
    if content.startswith("---\n"):
        return content
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + content.strip() + "\n"


def init_dirs(args: argparse.Namespace) -> None:
    root = orchestration_root(args)
    for directory in [
        "spec/active",
        "spec/archived",
        "plan/active",
        "plan/archived",
        "result/executor/active",
        "result/executor/reviewed",
        "result/executor/superseded",
        "result/executor/archived",
        "result/accepted/active",
        "result/accepted/superseded",
        "result/accepted/archived",
        "review/implementation/active",
        "review/implementation/superseded",
        "review/implementation/archived",
        "review/final/active",
        "review/final/archived",
        "docs",
    ]:
        (root / directory).mkdir(parents=True, exist_ok=True)


def rel(path: Path, args: argparse.Namespace) -> str:
    return path.resolve().relative_to(resolve_workspace_root(args)).as_posix()


def artifact_path_from_row(row: dict[str, object], args: argparse.Namespace) -> Path:
    raw_path = str(row.get("path", ""))
    if not raw_path:
        raise SystemExit(f"Index row has no path: {row}")
    return resolve_workspace_root(args) / raw_path


def move_to_archive(path: Path, active_root: Path, archived_root: Path) -> Path:
    relative = path.resolve().relative_to(active_root.resolve())
    target = archived_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    return target


def count_by_status(
    rows: list[dict[str, object]], *, status_key: str = "status"
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get(status_key, "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def policy_for_directive(name: str) -> str:
    if name not in DIRECTIVE_POLICY_MAP:
        raise SystemExit(f"Unknown retrieval policy for directive: {name}")
    return DIRECTIVE_POLICY_MAP[name]


def retrieval_policy_intent(name: str) -> dict[str, str]:
    return {
        "directive": name,
        "policy": policy_for_directive(name),
        "discovery": "neutral-cross-stage",
        "usage": "classification-output-intent",
    }


def artifact_mentions_retrieval_without_roles(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "retrieval" not in text.lower():
        return False
    return not any(role in text for role in RETRIEVAL_ROLES)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def keep_summarizing_root() -> Path:
    return repository_root() / "keep-summarizing"
