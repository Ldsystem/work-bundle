#!/usr/bin/env python3
"""Deterministic helpers for the keep-summarizing skill."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path


def _infrastructure_module():
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


LEAF_PERSPECTIVES = {
    "background/domain-concepts",
    "background/business-context",
    "background/user-roles",
    "background/glossary",
    "requirements/functional",
    "requirements/non-functional",
    "requirements/constraints",
    "requirements/non-goals",
    "architecture/system-boundary",
    "architecture/component-boundary",
    "architecture/dependency-direction",
    "architecture/source-of-truth",
    "architecture/decisions",
    "architecture/patterns",
    "workflow/process-flow",
    "workflow/data-flow",
    "workflow/state-lifecycle",
    "workflow/user-flow",
    "data/data-model",
    "data/schema",
    "data/identifiers",
    "data/relationships",
    "data/lineage",
    "data/migration",
    "interfaces/api-contract",
    "interfaces/event-contract",
    "interfaces/file-contract",
    "interfaces/error-contract",
    "interfaces/compatibility",
    "implementation/backend/runtime-framework",
    "implementation/backend/module-structure",
    "implementation/backend/service-responsibility",
    "implementation/backend/transaction-scheduling",
    "implementation/backend/control-flow",
    "implementation/backend/coding-rules",
    "implementation/frontend/runtime-framework",
    "implementation/frontend/page-routing",
    "implementation/frontend/component-structure",
    "implementation/frontend/state-management",
    "implementation/frontend/api-client",
    "implementation/frontend/interaction-behavior",
    "implementation/frontend/ui-ux",
    "implementation/database/engine-constraints",
    "implementation/database/table-design",
    "implementation/database/indexing-query",
    "implementation/database/sql-compatibility",
    "implementation/cache/key-format",
    "implementation/cache/ttl-invalidation",
    "implementation/cache/serialization-compression",
    "implementation/cache/stampede-protection",
    "implementation/async-messaging/event-schema",
    "implementation/async-messaging/consumer-processing",
    "implementation/async-messaging/watermark-lateness",
    "implementation/async-messaging/replay-idempotency",
    "quality/validation",
    "quality/testing-strategy",
    "quality/test-cases",
    "quality/edge-cases",
    "quality/performance",
    "quality/observability",
    "operations/deployment",
    "operations/configuration",
    "operations/backup-restore",
    "operations/resource-limits",
    "operations/startup-shutdown",
    "operations/troubleshooting",
    "operations/security-permission",
}

LEGACY_PERSPECTIVES = {
    "process-flow",
    "data-flow",
    "architecture",
    "code-structure",
    "decisions",
    "patterns",
    "glossary",
}
ALL_PERSPECTIVES = LEAF_PERSPECTIVES | LEGACY_PERSPECTIVES
QUESTION_STATUSES = {"open", "resolved", "superseded"}
DEFAULT_GIT_COMMANDS = {"status", "diff", "log", "add", "commit", "branch", "tag", "restore"}
DEFAULT_STATUSES = {"draft", "proposed", "confirmed", "implemented", "current", "superseded", "deprecated", "rejected"}
DEFAULT_SENSITIVITIES = {"normal", "confidential", "secret"}
DEFAULT_EXCLUDE_STATUS = {"draft", "proposed", "superseded", "deprecated", "rejected"}
DEFAULT_EXCLUDE_SENSITIVITY = {"confidential", "secret"}
PROTECTED_GIT_PATTERNS = (("reset", "--hard"), ("push", "--force"), ("push", "-f"), ("branch", "-D"), ("branch", "-d"))

LIFECYCLE_PATH_SEGMENTS = {
    "tender": "tender",
    "investigation": "investigation",
    "customer_design": "customer-design",
    "bidding": "bidding",
    "development_design": "development-design",
    "implementation": "implementation",
    "deployment": "deployment",
    "go_live_delivery": "go-live-delivery",
    "operation": "operation",
}
PATH_SEGMENT_LIFECYCLES = {value: key for key, value in LIFECYCLE_PATH_SEGMENTS.items()}
SOURCE_TYPES = {"discussion", "tender_doc", "investigation_note", "design_doc", "bid_doc", "source_code", "handoff", "plan_review", "deployment_record", "delivery_record", "runtime_observation"}
EVIDENCE_TYPES = {"specification", "plan", "handoff", "plan_review", "source_code", "deployment_record", "delivery_record", "runtime_observation", "source_note"}
EVIDENCE_RELATIONS = {"confirms", "implements", "derives_from", "validates", "supersedes", "observes"}
AUTHORITY_STATUSES = {"confirmed", "implemented", "current"}
NON_AUTHORITY_STATUSES = {"draft", "proposed", "superseded", "deprecated", "rejected"}
BLOCKED_STATUSES = {"superseded", "deprecated", "rejected"}
RETRIEVAL_POLICY_HINTS = {
    "implementation_spec",
    "implementation_plan",
    "execution",
    "customer_spec",
    "bidding",
    "deployment",
    "operation",
}
FORBIDDEN_SCRIPT_SEMANTIC_FIELDS = {
    "supports_current_purpose",
    "opposes_current_purpose",
    "conflict",
    "semantic_relevance",
    "authority_decision",
    "truth_confidence",
    "recommended_action",
    "should_block",
}
VECTOR_INDEX_STATUS_FILE = "vector-index-status.json"
VECTOR_INDEX_ARTIFACT_FILE = "vector-index.jsonl"

V3_PERSPECTIVES_BY_LIFECYCLE = {
    "tender": {"background", "requirements", "constraints", "deliverables", "glossary"},
    "investigation": {"scope-of-work", "user-portrait", "business-boundary", "process-flow", "performance-requirement", "integration-landscape", "risks", "constraints"},
    "customer_design": {"business-boundary", "process-flow", "functional-modules", "user-flow", "ui-prototype", "acceptance-criteria", "non-goals"},
    "bidding": {"committed-scope", "exclusions", "deliverables", "milestones", "assumptions", "risks"},
    "development_design": {"architecture/system-boundary", "architecture/component-boundary", "architecture/dependency-direction", "architecture/source-of-truth", "architecture/decisions", "architecture/patterns", "workflow/process-flow", "workflow/data-flow", "workflow/state-lifecycle", "workflow/control-flow", "data/data-model", "data/schema", "data/identifiers", "data/relationships", "data/lineage", "data/migration", "interfaces/api-contract", "interfaces/event-contract", "interfaces/file-contract", "interfaces/error-contract", "interfaces/compatibility", "implementation/backend", "implementation/frontend", "implementation/database", "implementation/cache", "implementation/async-messaging", "quality/requirements", "quality/validation", "quality/testing-strategy", "quality/edge-cases", "quality/performance", "quality/observability"},
    "implementation": {"implemented-features", "reusable-functions", "module-structure", "code-structure", "coding-rules", "tests", "known-limitations", "implementation-decisions"},
    "deployment": {"topology", "configuration", "packaging", "migration", "backup-restore", "resource-limits", "rollout-rollback", "startup-shutdown", "security-permission"},
    "go_live_delivery": {"acceptance-result", "delivery-scope", "handover", "training", "final-exclusions", "support-boundary", "production-cutover"},
    "operation": {"runtime-observation", "troubleshooting", "incidents", "performance", "maintenance", "optimization", "security-audit"},
}
V3_LEAF_PERSPECTIVES = {f"{LIFECYCLE_PATH_SEGMENTS[lifecycle]}/{leaf}" for lifecycle, leaves in V3_PERSPECTIVES_BY_LIFECYCLE.items() for leaf in leaves}


def skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def knowledge_root() -> Path:
    return skill_root() / "knowledge"


def registry_file(args: argparse.Namespace | None = None) -> Path:
    return _infrastructure.resolve_project_registry_path()


def work_bundle_knowledge_root(workspace_root: Path) -> Path:
    return workspace_root.resolve() / ".work-bundle" / "knowledge"


def _anchor_context(**selectors: object):
    try:
        return _infrastructure.resolve_anchor_context(**selectors)
    except _infrastructure.InfrastructureError as exc:
        raise SystemExit(exc.code) from exc


def resolve_workspace_root(start: Path) -> Path:
    """Resolve a containing current workspace through schema and binding authority."""
    return _anchor_context(cwd=start).workspace_root


def read_project_slug(root: Path, fallback: str) -> str:
    project_yaml = root / "project.yaml"
    if not project_yaml.exists():
        return fallback
    for line in project_yaml.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("slug:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                return value
    return fallback


def registry_projects(path: Path) -> list[dict[str, object]]:
    document = _infrastructure.load_project_registry()
    projects = document.get("projects")
    return [dict(item) for item in projects if isinstance(item, dict)] if isinstance(projects, list) else []


def resolve_knowledge_base(args: argparse.Namespace | None = None) -> tuple[Path, str]:
    if args is not None:
        explicit_root = getattr(args, "knowledge_root", None)
        if explicit_root:
            return Path(explicit_root).resolve(), "work-bundle"
        workspace_arg = getattr(args, "workspace_root", None)
        if workspace_arg:
            context = _anchor_context(workspace_root=workspace_arg)
            return work_bundle_knowledge_root(context.workspace_root), "work-bundle"
        project_root = getattr(args, "project_root", None)
        if project_root:
            explicit = Path(project_root).expanduser().resolve()
            context = _anchor_context(project_root=explicit, cwd=explicit)
            return work_bundle_knowledge_root(context.workspace_root), "work-bundle"
        cwd_arg = getattr(args, "cwd", None)
        if cwd_arg:
            context = _anchor_context(cwd=Path(cwd_arg))
            return work_bundle_knowledge_root(context.workspace_root), "work-bundle"
    context = _anchor_context(cwd=Path(os.getcwd()))
    return work_bundle_knowledge_root(context.workspace_root), "work-bundle"


def project_dir(project: str, args: argparse.Namespace | None = None) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", project):
        raise SystemExit(f"Invalid project slug: {project}")
    base, mode = resolve_knowledge_base(args)
    root = base.resolve() if mode == "work-bundle" else (base / project).resolve()
    allowed = base.resolve()
    if allowed != root and allowed not in root.parents:
        raise SystemExit("Resolved project path is outside knowledge root.")
    return root


def now_date() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def now_ts() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "untitled"


def is_relative_to(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


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
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            existing = data.setdefault(current_key, [])
            if existing == "":
                data[current_key] = []
                existing = data[current_key]
            if isinstance(existing, list):
                existing.append(line[4:].strip())
            continue
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            if value == "[]":
                data[current_key] = []
            elif value.lower() == "true":
                data[current_key] = True
            elif value.lower() == "false":
                data[current_key] = False
            else:
                data[current_key] = value
    return data, body


def lifecycle_to_path_segment(lifecycle_stage: str) -> str:
    return LIFECYCLE_PATH_SEGMENTS.get(lifecycle_stage, lifecycle_stage)


def path_segment_to_lifecycle(segment: str) -> str:
    return PATH_SEGMENT_LIFECYCLES.get(segment, segment)


def lifecycle_from_perspective(perspective: str) -> str:
    return path_segment_to_lifecycle(perspective.split("/", 1)[0])


def is_v3_perspective(perspective: object) -> bool:
    return isinstance(perspective, str) and perspective in V3_LEAF_PERSPECTIVES


def has_frontmatter_list(fm: dict[str, object], key: str) -> bool:
    value = fm.get(key)
    if isinstance(value, list):
        return len(value) > 0
    return bool(value)


def extract_section(text: str, name: str) -> str:
    lines = text.splitlines()
    collected: list[str] = []
    in_section = False
    for line in lines:
        if re.match(r"^[A-Za-z_][\w-]*:\s*$", line):
            key = line.split(":", 1)[0]
            if key == name:
                in_section = True
                collected.append(line)
                continue
            if in_section:
                break
        elif in_section:
            collected.append(line)
    return "\n".join(collected)


def yaml_scalar(section: str, name: str, default: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", section, flags=re.MULTILINE)
    return match.group(1).strip().strip('"') if match else default


def yaml_list(section: str, name: str, default: set[str]) -> set[str]:
    lines = section.splitlines()
    values: list[str] = []
    in_list = False
    base_indent = 0
    for line in lines:
        match = re.match(rf"^(\s*){re.escape(name)}:\s*(.*)$", line)
        if match:
            in_list = True
            base_indent = len(match.group(1))
            inline = match.group(2).strip()
            if inline and inline != "[]":
                values.extend(item.strip() for item in inline.strip("[]").split(",") if item.strip())
            continue
        if in_list:
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent <= base_indent and not line.lstrip().startswith("- "):
                break
            item = re.match(r"^\s*-\s+(.+?)\s*$", line)
            if item:
                values.append(item.group(1).strip().strip('"'))
    return set(values) if values else set(default)


def project_config(root: Path) -> dict[str, object]:
    config: dict[str, object] = {
        "statuses": set(DEFAULT_STATUSES),
        "default_sensitivity": "normal",
        "exclude_status": set(DEFAULT_EXCLUDE_STATUS),
        "exclude_sensitivity": set(DEFAULT_EXCLUDE_SENSITIVITY),
        "allowed_git_commands": set(DEFAULT_GIT_COMMANDS),
    }
    project_yaml = root / "project.yaml"
    if not project_yaml.exists():
        return config
    text = project_yaml.read_text(encoding="utf-8")
    curation = extract_section(text, "curation")
    embedding = extract_section(text, "embedding")
    knowledge_repo = extract_section(text, "knowledge_repo")
    config["statuses"] = yaml_list(curation, "statuses", DEFAULT_STATUSES)
    config["default_sensitivity"] = yaml_scalar(curation, "default_sensitivity", "normal")
    config["exclude_status"] = yaml_list(embedding, "exclude_status", DEFAULT_EXCLUDE_STATUS)
    config["exclude_sensitivity"] = yaml_list(embedding, "exclude_sensitivity", DEFAULT_EXCLUDE_SENSITIVITY)
    config["allowed_git_commands"] = yaml_list(knowledge_repo, "allowed_commands", DEFAULT_GIT_COMMANDS)
    return config


def validate_leaf_perspective(perspective: str) -> None:
    if perspective in LEAF_PERSPECTIVES or perspective in V3_LEAF_PERSPECTIVES:
        return
    if perspective in LEGACY_PERSPECTIVES:
        raise SystemExit(f"Legacy broad perspective is read-only/migration-only for new writes: {perspective}")
    raise SystemExit(f"Invalid perspective: {perspective}")


def write_project_yaml(root: Path, project: str, source: str | None) -> None:
    root_path = ".work-bundle/knowledge" if root.name == "knowledge" and root.parent.name == ".work-bundle" else f"knowledge/{project}"
    content = f"""project:
  slug: {project}
  name: {project}
  aliases: []
  source_repositories:
    - path: {source or ""}
      remote: ""
  domain: engineering
  primary_languages:
    - en

knowledge_repo:
  root: {root_path}
  git:
    auto_commit: false
    default_branch: main
    allowed_commands:
      - status
      - diff
      - log
      - add
      - commit
      - branch
      - tag
      - restore
    protected_operations:
      - reset-hard
      - force-push
      - delete-branch
      - delete-durable-note

mcp:
  allowed_roots:
    - {root_path}
  deny_non_knowledge_paths: true
  require_dry_run_for_overwrite: true

curation:
  default_visibility: private
  default_sensitivity: normal
  statuses:
    - draft
    - proposed
    - confirmed
    - implemented
    - current
    - superseded
    - deprecated
    - rejected
  stale_after_days:
    context_pack: 30
    derived_document: 14

embedding:
  enabled: true
  exclude_sensitivity:
    - confidential
    - secret
  exclude_status:
    - draft
    - proposed
    - superseded
    - deprecated
    - rejected

open_questions:
  root: open-questions
  registry: indexes/open-question-registry.jsonl
  watch_context: true
  statuses:
    - open
    - resolved
    - superseded
"""
    (root / "project.yaml").write_text(content, encoding="utf-8")




def note_id(perspective: str, title: str) -> str:
    return f"ks-{perspective.replace('/', '-')}-{slugify(title)}"


def question_id(perspective: str, title: str) -> str:
    return f"oq-{perspective.replace('/', '-')}-{slugify(title)}"


def csv_items(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def yaml_list_field(name: str, values: object) -> str:
    if not isinstance(values, list) or not values:
        return f"{name}: []"
    return f"{name}:\n" + "\n".join(f"  - {item}" for item in values)
