#!/usr/bin/env python3
"""Deterministic helpers for the orchestrator skill."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
from pathlib import Path


SPEC_STATUSES = {"draft", "active", "implemented", "reviewed", "superseded", "archived"}
PLAN_STATUSES = {"Planned", "In progress", "Completed", "Deprecated", "On Hold"}
HANDOFF_STATUSES = {"active", "reviewed", "archived", "superseded"}
HANDOFF_TYPES = {"orchestration", "executor-result"}
RETRIEVAL_ROLES = {"authority", "candidate", "background", "blocked"}
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


def project_root(args: argparse.Namespace) -> Path:
    if args.project_root:
        return Path(args.project_root).resolve()
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".work-bundle").exists():
            return candidate
    raise SystemExit("No project root found. Pass --project-root or run inside a work bundle.")


def work_bundle(args: argparse.Namespace) -> Path:
    return project_root(args) / ".work-bundle"


def orchestration_root(args: argparse.Namespace) -> Path:
    return work_bundle(args) / "orchestration"


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
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    data: dict[str, object] = {}
    for line in raw.splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data, body


def write_text_safely(path: Path, content: str, args: argparse.Namespace) -> None:
    target = ensure_under_orchestration(path, args)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + "\n", encoding="utf-8")


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
        "handoff/orchestration/active",
        "handoff/orchestration/archived",
        "handoff/executor/active",
        "handoff/executor/archived",
        "docs",
    ]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    for index in ["spec/index.jsonl", "plan/index.jsonl", "handoff/index.jsonl"]:
        path = root / index
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)


def rel(path: Path, args: argparse.Namespace) -> str:
    return path.resolve().relative_to(project_root(args)).as_posix()


def artifact_path_from_row(row: dict[str, object], args: argparse.Namespace) -> Path:
    raw_path = str(row.get("path", ""))
    if not raw_path:
        raise SystemExit(f"Index row has no path: {row}")
    return project_root(args) / raw_path


def move_to_archive(path: Path, active_root: Path, archived_root: Path) -> Path:
    relative = path.resolve().relative_to(active_root.resolve())
    target = archived_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    return target


def count_by_status(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def policy_for_directive(name: str) -> str:
    if name not in DIRECTIVE_POLICY_MAP:
        raise SystemExit(f"Unknown retrieval policy for directive: {name}")
    return DIRECTIVE_POLICY_MAP[name]


def artifact_mentions_retrieval_without_roles(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "retrieval" not in text.lower():
        return False
    return not any(role in text for role in RETRIEVAL_ROLES)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def keep_summarizing_root() -> Path:
    return repository_root() / "keep-summarizing"


