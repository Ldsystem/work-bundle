#!/usr/bin/env python3
"""Deterministic helpers for the keep-summarizing skill."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path


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


def default_registry_file() -> Path:
    return Path.home() / ".work-bundle" / "registry" / "projects.yaml"


def registry_file(args: argparse.Namespace | None = None) -> Path:
    if args is not None:
        explicit = getattr(args, "registry_file", None)
        if explicit:
            return Path(explicit).expanduser().resolve()
    env_path = os.environ.get("KS_PROJECT_REGISTRY")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return default_registry_file()


def work_bundle_knowledge_root(project_root: Path) -> Path:
    return project_root.resolve() / ".work-bundle" / "knowledge"


def find_work_bundle_knowledge(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        root = candidate / ".work-bundle" / "knowledge"
        if root.exists():
            return root.resolve()
    return None


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


def yaml_quote(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    if re.search(r"[:#\n\r\t]|^\s|\s$|^-|^\[", text):
        return json.dumps(text, ensure_ascii=False)
    return text


def parse_yaml_value(value: str) -> object:
    value = value.strip()
    if value == "[]":
        return []
    if value in {"true", "false"}:
        return value == "true"
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    return value


def registry_projects(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    projects: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_list: str | None = None
    current_repo: dict[str, object] | None = None
    in_projects = False
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line == "projects:":
            in_projects = True
            continue
        if not in_projects:
            continue
        project_start = re.match(r"^\s{2}-\s+slug:\s*(.+)$", line)
        if project_start:
            current = {"slug": str(parse_yaml_value(project_start.group(1))), "aliases": [], "source_repositories": []}
            projects.append(current)
            current_list = None
            current_repo = None
            continue
        if current is None:
            continue
        top_field = re.match(r"^\s{4}([A-Za-z_][\w-]*):\s*(.*)$", line)
        if top_field:
            key, raw = top_field.group(1), top_field.group(2)
            current_repo = None
            if raw:
                current[key] = parse_yaml_value(raw)
                current_list = None
            else:
                current.setdefault(key, [])
                current_list = key
            continue
        list_scalar = re.match(r"^\s{6}-\s+(.+)$", line)
        if list_scalar and current_list == "aliases":
            aliases = current.setdefault("aliases", [])
            if isinstance(aliases, list):
                aliases.append(str(parse_yaml_value(list_scalar.group(1))))
            continue
        repo_start = re.match(r"^\s{6}-\s+path:\s*(.+)$", line)
        if repo_start and current_list == "source_repositories":
            repos = current.setdefault("source_repositories", [])
            current_repo = {"path": str(parse_yaml_value(repo_start.group(1)))}
            if isinstance(repos, list):
                repos.append(current_repo)
            continue
        repo_field = re.match(r"^\s{8}([A-Za-z_][\w-]*):\s*(.*)$", line)
        if repo_field and current_repo is not None:
            current_repo[repo_field.group(1)] = parse_yaml_value(repo_field.group(2))
    return projects


def write_registry_projects(path: Path, projects: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["projects:"]
    for project in sorted(projects, key=lambda item: str(item.get("slug", ""))):
        lines.append(f"  - slug: {yaml_quote(project.get('slug', ''))}")
        lines.append(f"    name: {yaml_quote(project.get('name', project.get('slug', '')))}")
        lines.append(f"    work_bundle_root: {yaml_quote(project.get('work_bundle_root', ''))}")
        lines.append(f"    knowledge_root: {yaml_quote(project.get('knowledge_root', ''))}")
        aliases = project.get("aliases", [])
        if isinstance(aliases, list) and aliases:
            lines.append("    aliases:")
            for alias in aliases:
                lines.append(f"      - {yaml_quote(alias)}")
        else:
            lines.append("    aliases: []")
        repos = project.get("source_repositories", [])
        lines.append("    source_repositories:")
        if isinstance(repos, list) and repos:
            for repo in repos:
                if not isinstance(repo, dict):
                    continue
                lines.append(f"      - path: {yaml_quote(repo.get('path', ''))}")
                lines.append(f"        work_dir: {'true' if repo.get('work_dir') else 'false'}")
                lines.append(f"        remote: {yaml_quote(repo.get('remote', ''))}")
        lines.append(f"    status: {yaml_quote(project.get('status', 'active'))}")
        lines.append(f"    updated_at: {yaml_quote(project.get('updated_at', now_date()))}")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def project_registry_entry(project: str, args: argparse.Namespace | None = None) -> dict[str, object] | None:
    for entry in registry_projects(registry_file(args)):
        if entry.get("slug") == project:
            return entry
        aliases = entry.get("aliases", [])
        if isinstance(aliases, list) and project in aliases:
            return entry
    return None


def registry_entry_for_cwd(cwd: Path, args: argparse.Namespace | None = None) -> dict[str, object] | None:
    cwd = cwd.resolve()
    for entry in registry_projects(registry_file(args)):
        for key in ["work_bundle_root", "knowledge_root"]:
            value = entry.get(key)
            if value:
                candidate = Path(str(value)).expanduser()
                if candidate.exists() and is_relative_to(cwd, candidate):
                    return entry
        repos = entry.get("source_repositories", [])
        if isinstance(repos, list):
            for repo in repos:
                if isinstance(repo, dict) and repo.get("path"):
                    candidate = Path(str(repo["path"])).expanduser()
                    if candidate.exists() and is_relative_to(cwd, candidate):
                        return entry
    return None


def registry_knowledge_root_for_project(project: str, args: argparse.Namespace | None = None) -> Path | None:
    entry = project_registry_entry(project, args)
    if not entry:
        return None
    root = entry.get("knowledge_root")
    return Path(str(root)).expanduser().resolve() if root else None


def resolve_knowledge_base(args: argparse.Namespace | None = None) -> tuple[Path, str]:
    if args is not None:
        explicit_root = getattr(args, "knowledge_root", None)
        if explicit_root:
            return Path(explicit_root).resolve(), "work-bundle"
        project_root = getattr(args, "project_root", None)
        if project_root:
            return work_bundle_knowledge_root(Path(project_root)), "work-bundle"
        cwd_arg = getattr(args, "cwd", None)
        if cwd_arg:
            found = find_work_bundle_knowledge(Path(cwd_arg))
            if found:
                return found, "work-bundle"
            entry = registry_entry_for_cwd(Path(cwd_arg), args)
            if entry and entry.get("knowledge_root"):
                return Path(str(entry["knowledge_root"])).expanduser().resolve(), "registry"
    found = find_work_bundle_knowledge(Path(os.getcwd()))
    if found:
        return found, "work-bundle"
    entry = registry_entry_for_cwd(Path(os.getcwd()), args)
    if entry and entry.get("knowledge_root"):
        return Path(str(entry["knowledge_root"])).expanduser().resolve(), "registry"
    raise SystemExit("No .work-bundle/knowledge root found. Pass --project-root or --knowledge-root explicitly.")


def project_dir(project: str, args: argparse.Namespace | None = None) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", project):
        raise SystemExit(f"Invalid project slug: {project}")
    if args is not None and not getattr(args, "knowledge_root", None) and not getattr(args, "project_root", None):
        registered = registry_knowledge_root_for_project(project, args)
        if registered:
            return registered
    base, mode = resolve_knowledge_base(args)
    root = base.resolve() if mode in {"work-bundle", "registry"} else (base / project).resolve()
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

