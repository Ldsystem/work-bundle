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
    return Path(__file__).resolve().parents[1]


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


def source_repositories_for_registration(project_root: Path, source_values: list[str] | None = None) -> list[dict[str, object]]:
    sources = source_values or [str(project_root)]
    repos: list[dict[str, object]] = []
    for index, source in enumerate(sources):
        repos.append({"path": str(Path(source).expanduser().resolve()), "work_dir": index == 0, "remote": ""})
    return repos


def upsert_registry_project(
    project: str,
    project_root: Path,
    args: argparse.Namespace | None = None,
    name: str | None = None,
    aliases: list[str] | None = None,
    sources: list[str] | None = None,
) -> dict[str, object]:
    path = registry_file(args)
    projects = registry_projects(path)
    canonical = project
    for entry in projects:
        entry_aliases = entry.get("aliases", [])
        if entry.get("slug") == project or (isinstance(entry_aliases, list) and project in entry_aliases):
            canonical = str(entry.get("slug", project))
            break
    work_bundle = project_root.resolve() / ".work-bundle"
    knowledge = work_bundle / "knowledge"
    aliases = aliases or []
    entry = {
        "slug": canonical,
        "name": name or canonical,
        "work_bundle_root": str(work_bundle),
        "knowledge_root": str(knowledge),
        "aliases": aliases,
        "source_repositories": source_repositories_for_registration(project_root, sources),
        "status": "active",
        "updated_at": now_date(),
    }
    updated = False
    next_projects: list[dict[str, object]] = []
    for item in projects:
        if item.get("slug") == canonical:
            next_projects.append(entry)
            updated = True
        else:
            next_projects.append(item)
    if not updated:
        next_projects.append(entry)
    write_registry_projects(path, next_projects)
    return entry


def cmd_register_project(args: argparse.Namespace) -> None:
    project_root = Path(args.project_root).expanduser().resolve()
    aliases = args.alias or []
    sources = args.source or [str(project_root)]
    entry = upsert_registry_project(args.project, project_root, args, name=args.name, aliases=aliases, sources=sources)
    print(json.dumps(entry, ensure_ascii=False))


def cmd_unregister_project(args: argparse.Namespace) -> None:
    path = registry_file(args)
    projects = registry_projects(path)
    kept = []
    removed = False
    for entry in projects:
        aliases = entry.get("aliases", [])
        if entry.get("slug") == args.project or (isinstance(aliases, list) and args.project in aliases):
            removed = True
            continue
        kept.append(entry)
    write_registry_projects(path, kept)
    print("removed" if removed else "not found")


def cmd_list_projects(args: argparse.Namespace) -> None:
    for entry in registry_projects(registry_file(args)):
        print(json.dumps(entry, ensure_ascii=False))


def registry_issues(args: argparse.Namespace) -> list[str]:
    path = registry_file(args)
    if not path.exists():
        return [f"missing registry file: {path}"]
    projects = registry_projects(path)
    if not projects:
        return ["missing projects"]
    issues: list[str] = []
    seen_slugs: dict[str, str] = {}
    seen_aliases: dict[str, str] = {}
    for entry in projects:
        slug = str(entry.get("slug", ""))
        if not slug:
            issues.append("project entry missing slug")
            continue
        if slug in seen_slugs:
            issues.append(f"duplicate slug {slug}")
        seen_slugs[slug] = slug
        aliases = entry.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                alias_text = str(alias)
                if alias_text in seen_aliases:
                    issues.append(f"duplicate alias {alias_text}: {seen_aliases[alias_text]} and {slug}")
                seen_aliases[alias_text] = slug
                if alias_text in seen_slugs and alias_text != slug:
                    issues.append(f"alias collides with slug {alias_text}: {slug}")
        root_value = entry.get("knowledge_root")
        if not root_value:
            issues.append(f"missing knowledge_root: {slug}")
            continue
        knowledge = Path(str(root_value)).expanduser()
        if not knowledge.exists():
            issues.append(f"missing knowledge_root path: {slug} -> {knowledge}")
            continue
        project_yaml = knowledge / "project.yaml"
        if not project_yaml.exists():
            issues.append(f"missing project.yaml: {slug}")
        else:
            actual_slug = read_project_slug(knowledge, "")
            if actual_slug != slug:
                issues.append(f"project.yaml slug mismatch: registry {slug}, project.yaml {actual_slug}")
        repos = entry.get("source_repositories", [])
        if isinstance(repos, list):
            for repo in repos:
                if isinstance(repo, dict) and repo.get("path"):
                    source = Path(str(repo["path"])).expanduser()
                    if not source.exists():
                        issues.append(f"missing source path: {slug} -> {source}")
    return issues


def cmd_registry_doctor(args: argparse.Namespace) -> None:
    issues = registry_issues(args)
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print("ok")


def cmd_init(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    root.mkdir(parents=True, exist_ok=True)
    for directory in [
        *[f"notes/{perspective}" for perspective in sorted(LEAF_PERSPECTIVES)],
        "open-questions",
        "context-packs",
        "directives",
        "indexes",
        ".keep-summarizing/locks",
        ".keep-summarizing/cache/embeddings",
    ]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    for perspective in sorted(LEAF_PERSPECTIVES):
        (root / "open-questions" / perspective).mkdir(parents=True, exist_ok=True)
    if not (root / "project.yaml").exists():
        write_project_yaml(root, args.project, args.source)
    _, mode = resolve_knowledge_base(args)
    if mode == "legacy" and not (root / ".git").exists():
        subprocess.run(["git", "init"], cwd=root, check=True)
    cmd_index(argparse.Namespace(project=args.project, project_root=getattr(args, "project_root", None), knowledge_root=getattr(args, "knowledge_root", None), cwd=getattr(args, "cwd", None)))
    project_root = Path(getattr(args, "project_root", "") or root.parent.parent).resolve()
    upsert_registry_project(args.project, project_root, args, name=args.project, sources=[args.source] if args.source else [str(project_root)])
    print(str(root))


def cmd_resolve(args: argparse.Namespace) -> None:
    cwd = Path(args.cwd or os.getcwd()).resolve()
    registry_entry = registry_entry_for_cwd(cwd, args)
    if registry_entry:
        print(registry_entry.get("slug"))
        return
    base, mode = resolve_knowledge_base(args)
    if mode in {"work-bundle", "registry"}:
        print(read_project_slug(base, base.parent.parent.name))
        return
    for project_yaml in knowledge_root().glob("*/project.yaml"):
        root = project_yaml.parent.resolve()
        if cwd == root or root in cwd.parents:
            print(project_yaml.parent.name)
            return
        text = project_yaml.read_text(encoding="utf-8")
        if str(cwd) in text:
            print(project_yaml.parent.name)
            return
    raise SystemExit("No matching project knowledge repo found.")


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


def cmd_write_note(args: argparse.Namespace) -> None:
    validate_leaf_perspective(args.perspective)
    root = project_dir(args.project, args)
    config = project_config(root)
    content = Path(args.content_file).read_text(encoding="utf-8")
    title_slug = slugify(args.title)
    path = root / "notes" / args.perspective / f"{title_slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not content.startswith("---\n"):
        nid = note_id(args.perspective, args.title)
        lifecycle_stage = args.lifecycle_stage or lifecycle_from_perspective(args.perspective)
        source_type = args.source_type or "discussion"
        content = f"""---
id: {nid}
title: {args.title}
lifecycle_stage: {lifecycle_stage}
perspective: {args.perspective}
status: draft
source_type: {source_type}
summary: ""
owner: keep-summarizing
created_at: {now_date()}
updated_at: {now_date()}
visibility: private
sensitivity: {config["default_sensitivity"]}
tags: []
evidence: []
related_notes: []
supersedes: []
superseded_by: []
embedding:
  include: true
  chunk_strategy: heading
---

# {args.title}

{content.rstrip()}
"""
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    cmd_index(args)
    print(str(path))


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
        include = status not in config["exclude_status"] and sensitivity not in config["exclude_sensitivity"]
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
    build_open_question_index(root, args.project)
    print(f"indexed {len(docs)} documents")


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


def cmd_git(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    config = project_config(root)
    if not (root / ".git").exists():
        raise SystemExit("Project knowledge repo is not a Git repository.")
    if not args.git_args:
        raise SystemExit("Missing Git arguments.")
    subcommand = args.git_args[0]
    if subcommand not in config["allowed_git_commands"]:
        raise SystemExit(f"Git subcommand is not allowlisted: {subcommand}")
    for pattern in PROTECTED_GIT_PATTERNS:
        if tuple(args.git_args[: len(pattern)]) == pattern:
            raise SystemExit(f"Protected Git operation requires explicit approval: {' '.join(pattern)}")
    result = subprocess.run(["git", *args.git_args], cwd=root, text=True)
    raise SystemExit(result.returncode)


def cmd_add_question(args: argparse.Namespace) -> None:
    validate_leaf_perspective(args.perspective)
    root = project_dir(args.project, args)
    body = Path(args.content_file).read_text(encoding="utf-8").strip()
    qid = question_id(args.perspective, args.title)
    path = root / "open-questions" / args.perspective / f"{slugify(args.title)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    trigger_terms = csv_items(args.trigger_terms)
    source_note_ids = csv_items(args.source_note_ids)
    content = f"""---
id: {qid}
title: {args.title}
perspective: {args.perspective}
status: open
created_at: {now_date()}
updated_at: {now_date()}
{yaml_list_field("source_note_ids", source_note_ids)}
{yaml_list_field("trigger_terms", trigger_terms)}
resolved_at:
resolved_by_note_id:
resolution_summary:
---

# {args.title}

## Question

{body}

## Why It Matters

- Track only because the user provided or confirmed this as future work.

## Resolution

Unresolved.
"""
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    build_open_question_index(root, args.project)
    print(str(path))


def load_open_question_registry(root: Path) -> list[dict[str, object]]:
    registry = root / "indexes" / "open-question-registry.jsonl"
    if not registry.exists():
        build_open_question_index(root, root.name)
    if not registry.exists():
        return []
    return [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_list_questions(args: argparse.Namespace) -> None:
    if args.status and args.status not in QUESTION_STATUSES:
        raise SystemExit(f"Invalid open-question status: {args.status}")
    if args.perspective and args.perspective not in ALL_PERSPECTIVES:
        raise SystemExit(f"Invalid perspective: {args.perspective}")
    root = project_dir(args.project, args)
    rows = load_open_question_registry(root)
    for row in rows:
        if args.status and row.get("status") != args.status:
            continue
        if args.perspective and row.get("perspective") != args.perspective:
            continue
        print(json.dumps(row, ensure_ascii=False))


def cmd_resolve_question(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    rows = load_open_question_registry(root)
    matches = [row for row in rows if row.get("id") == args.id]
    if not matches:
        raise SystemExit(f"Open question not found: {args.id}")
    path = root / str(matches[0]["path"])
    fm, body = read_front_matter(path)
    resolution = Path(args.resolution_file).read_text(encoding="utf-8").strip()
    title = str(fm.get("title", args.id))
    perspective = str(fm.get("perspective", ""))
    trigger_terms = fm.get("trigger_terms", [])
    source_note_ids = fm.get("source_note_ids", [])
    clean_body = body.strip()
    clean_body = clean_body.split("\n## Resolved Answer\n", 1)[0].rstrip()
    clean_body = clean_body.replace("## Resolution\n\nUnresolved.", "## Resolution\n\nResolved. See resolved answer below.")
    new_content = f"""---
id: {args.id}
title: {title}
perspective: {perspective}
status: resolved
created_at: {fm.get("created_at", now_date())}
updated_at: {now_date()}
{yaml_list_field("source_note_ids", source_note_ids)}
{yaml_list_field("trigger_terms", trigger_terms)}
resolved_at: {now_date()}
resolved_by_note_id: {args.resolved_by_note or ""}
resolution_summary: {resolution.splitlines()[0] if resolution else ""}
---

{clean_body}

## Resolved Answer

{resolution}
"""
    path.write_text(new_content.rstrip() + "\n", encoding="utf-8")
    build_open_question_index(root, args.project)
    print(str(path))


def cmd_match_questions(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    if args.text_file:
        haystack = Path(args.text_file).read_text(encoding="utf-8")
    else:
        haystack = args.text or ""
    haystack_lower = haystack.lower()
    rows = load_open_question_registry(root)
    matches = []
    for row in rows:
        if row.get("status") != "open" and not args.include_resolved:
            continue
        terms = row.get("trigger_terms", [])
        if not isinstance(terms, list):
            terms = []
        matched_terms = [term for term in terms if str(term).lower() in haystack_lower]
        if matched_terms:
            matched = dict(row)
            matched["matched_terms"] = matched_terms
            matches.append(matched)
    for row in matches:
        print(json.dumps(row, ensure_ascii=False))


def cmd_doctor(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    config = project_config(root)
    issues = []
    if (skill_root() / "knowledge").exists():
        issues.append("forbidden bundled runtime knowledge directory: knowledge/")
    if not (root / "project.yaml").exists():
        issues.append("missing project.yaml")
    ids: dict[str, str] = {}
    for path in markdown_files(root):
        fm, _ = read_front_matter(path)
        if not fm:
            issues.append(f"missing front matter: {path.relative_to(root)}")
            continue
        for key in ["id", "title", "perspective", "status", "visibility", "sensitivity", "created_at", "updated_at"]:
            if key not in fm:
                issues.append(f"missing {key}: {path.relative_to(root)}")
        issues.extend(v3_note_issues(root, path, fm))
        nid = str(fm.get("id", ""))
        if nid in ids:
            issues.append(f"duplicate id {nid}: {ids[nid]} and {path.relative_to(root)}")
        elif nid:
            ids[nid] = path.relative_to(root).as_posix()
        perspective = fm.get("perspective")
        if perspective in LEGACY_PERSPECTIVES:
            issues.append(f"legacy broad perspective used in curated note: {path.relative_to(root)}")
        elif perspective and perspective not in LEAF_PERSPECTIVES and perspective not in V3_LEAF_PERSPECTIVES:
            issues.append(f"invalid perspective {perspective}: {path.relative_to(root)}")
        if perspective and perspective in LEAF_PERSPECTIVES and f"notes/{perspective}/" not in path.relative_to(root).as_posix():
            issues.append(f"perspective/path mismatch: {path.relative_to(root)}")
        status = str(fm.get("status", ""))
        if status and status not in config["statuses"]:
            issues.append(f"invalid status {status}: {path.relative_to(root)}")
        sensitivity = str(fm.get("sensitivity", ""))
        if sensitivity and sensitivity not in DEFAULT_SENSITIVITIES:
            issues.append(f"invalid sensitivity {sensitivity}: {path.relative_to(root)}")
    for path in open_question_files(root):
        fm, _ = read_front_matter(path)
        if not fm:
            issues.append(f"missing front matter: {path.relative_to(root)}")
            continue
        for key in ["id", "title", "perspective", "status", "trigger_terms"]:
            if key not in fm:
                issues.append(f"missing {key}: {path.relative_to(root)}")
        status = str(fm.get("status", ""))
        if status and status not in QUESTION_STATUSES:
            issues.append(f"invalid open-question status {status}: {path.relative_to(root)}")
        perspective = fm.get("perspective")
        if perspective in LEGACY_PERSPECTIVES:
            issues.append(f"legacy broad perspective used in open question: {path.relative_to(root)}")
        elif perspective and perspective not in LEAF_PERSPECTIVES and perspective not in V3_LEAF_PERSPECTIVES:
            issues.append(f"invalid open-question perspective {perspective}: {path.relative_to(root)}")
        if perspective and f"open-questions/{perspective}/" not in path.relative_to(root).as_posix():
            issues.append(f"open-question perspective/path mismatch: {path.relative_to(root)}")
    for path in sorted(markdown_files(root) + open_question_files(root)):
        for target in re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", path.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+://", target) or target.startswith("mailto:") or target.startswith("?"):
                continue
            linked = (path.parent / target).resolve()
            if not is_relative_to(linked, root):
                issues.append(f"markdown link escapes knowledge root: {path.relative_to(root)} -> {target}")
            elif not linked.exists():
                issues.append(f"broken markdown link: {path.relative_to(root)} -> {target}")
    skill_paths = [
        path
        for path in skill_root().glob("**/*.md")
        if ".git" not in path.parts and "knowledge" not in path.relative_to(skill_root()).parts
    ]
    for path in sorted(skill_paths):
        for target in re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", path.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+://", target) or target.startswith("mailto:") or target.startswith("?"):
                continue
            linked = (path.parent / target).resolve()
            if not is_relative_to(linked, skill_root()):
                issues.append(f"skill markdown link escapes skill root: {path.relative_to(skill_root())} -> {target}")
            elif not linked.exists():
                issues.append(f"broken skill markdown link: {path.relative_to(skill_root())} -> {target}")
    doc_registry = root / "indexes" / "document-registry.jsonl"
    oq_registry = root / "indexes" / "open-question-registry.jsonl"
    sqlite_registry = root / "indexes" / "knowledge.sqlite"
    if markdown_files(root) and (not doc_registry.exists() or any(path.stat().st_mtime > doc_registry.stat().st_mtime for path in markdown_files(root))):
        issues.append("stale or missing document indexes")
    if markdown_files(root) and (not sqlite_registry.exists() or any(path.stat().st_mtime > sqlite_registry.stat().st_mtime for path in markdown_files(root))):
        issues.append("stale or missing SQLite FTS index")
    if open_question_files(root) and (not oq_registry.exists() or any(path.stat().st_mtime > oq_registry.stat().st_mtime for path in open_question_files(root))):
        issues.append("stale or missing open-question indexes")
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    if not project_registry_entry(args.project, args):
        print(f"warning: project is not registered: {args.project}")
    print("ok")


def cmd_output(args: argparse.Namespace) -> None:
    raise SystemExit("The reader-facing output directive moved to orchestrator create-document. Use orchestrator to write under .work-bundle/orchestration/docs/.")


def source_points(text: str) -> list[dict[str, str]]:
    points: list[dict[str, str]] = []
    headings: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if not pending:
            return
        excerpt = " ".join(item.strip() for item in pending if item.strip())
        pending.clear()
        if excerpt:
            points.append(
                {
                    "heading": " > ".join(headings) if headings else "(root)",
                    "excerpt": excerpt,
                }
            )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush()
            level = len(heading.group(1))
            headings = headings[: level - 1]
            headings.append(heading.group(2).strip())
            continue
        if not line:
            flush()
            continue
        if re.match(r"^([-*+]|\d+[.)])\s+", line):
            flush()
            points.append(
                {
                    "heading": " > ".join(headings) if headings else "(root)",
                    "excerpt": re.sub(r"^([-*+]|\d+[.)])\s+", "", line),
                }
            )
            continue
        pending.append(line)
    flush()
    return points


def cmd_breakdown_design(args: argparse.Namespace) -> None:
    text = Path(args.input).read_text(encoding="utf-8")
    default_parts = "development-design/architecture/decisions,development-design/workflow/data-flow,development-design/workflow/process-flow,development-design/architecture/patterns"
    parts = [part.strip() for part in (args.parts or default_parts).split(",") if part.strip()]
    for part in parts:
        validate_leaf_perspective(part)
    points = source_points(text)
    if not points:
        raise SystemExit("No meaningful source points found.")
    print("Validated scaffold only. Agent semantic review is required before persistence.")
    print("")
    print("| point_order | source_heading | suggested_leaf_perspective | suggested_note_title | target_path | source_excerpt |")
    print("| --- | --- | --- | --- | --- | --- |")
    for index, point in enumerate(points, start=1):
        perspective = parts[(index - 1) % len(parts)]
        title = point["heading"] if point["heading"] != "(root)" else f"Source Point {index}"
        title = re.sub(r"\s+", " ", title).strip()
        note_title = f"{title} Point {index}"
        target = f"notes/{perspective}/{slugify(note_title)}.md"
        heading = point["heading"].replace("|", "\\|")
        escaped_title = note_title.replace("|", "\\|")
        excerpt = point["excerpt"].replace("|", "\\|")
        print(f"| {index} | {heading} | {perspective} | {escaped_title} | {target} | {excerpt} |")
    print("")
    print(f"Coverage: {len(points)} source points mapped to atomic note/update candidates.")


LEGACY_PERSPECTIVE_MAP = {
    "architecture": "architecture/component-boundary",
    "code-structure": "implementation/backend/module-structure",
    "data-flow": "workflow/data-flow",
    "decisions": "architecture/decisions",
    "glossary": "background/glossary",
    "patterns": "architecture/patterns",
    "process-flow": "workflow/process-flow",
}


def remap_legacy_markdown(text: str, perspective: str) -> str:
    mapped = LEGACY_PERSPECTIVE_MAP.get(perspective, perspective)
    return re.sub(rf"^perspective:\s*{re.escape(perspective)}\s*$", f"perspective: {mapped}", text, flags=re.MULTILINE)


def copy_tree_markdown(source: Path, target: Path, remap_legacy_perspectives: bool = False) -> int:
    count = 0
    if not source.exists():
        return count
    for path in sorted(source.glob("**/*.md")):
        rel = path.relative_to(source)
        text = path.read_text(encoding="utf-8")
        if remap_legacy_perspectives and rel.parts:
            first = rel.parts[0]
            if first in LEGACY_PERSPECTIVE_MAP:
                mapped = Path(LEGACY_PERSPECTIVE_MAP[first])
                rel = mapped / Path(*rel.parts[1:])
                text = remap_legacy_markdown(text, first)
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_text(text, encoding="utf-8")
            count += 1
    return count


def cmd_migrate_legacy(args: argparse.Namespace) -> None:
    destination = project_dir(args.project, args)
    legacy_base = Path(args.legacy_root).resolve() if args.legacy_root else knowledge_root().resolve()
    legacy = (legacy_base / args.project).resolve()
    if not legacy.exists():
        raise SystemExit(f"Legacy knowledge repo not found: {legacy}")
    destination.mkdir(parents=True, exist_ok=True)
    legacy_project_yaml = legacy / "project.yaml"
    if legacy_project_yaml.exists():
        project_yaml = legacy_project_yaml.read_text(encoding="utf-8").replace(f"knowledge/{args.project}", ".work-bundle/knowledge")
        (destination / "project.yaml").write_text(project_yaml, encoding="utf-8")
    elif not (destination / "project.yaml").exists():
        write_project_yaml(destination, args.project, None)
    migrated = 0
    migrated += copy_tree_markdown(legacy / "notes", destination / "notes", remap_legacy_perspectives=True)
    migrated += copy_tree_markdown(legacy / "open-questions", destination / "open-questions", remap_legacy_perspectives=True)
    migrated += copy_tree_markdown(legacy / "context-packs", destination / "context-packs")
    handoff_source = legacy / "handoffs"
    if handoff_source.exists():
        project_root = Path(getattr(args, "project_root", "") or os.getcwd()).resolve()
        handoff_target = project_root / ".work-bundle" / "orchestration" / "handoff" / "orchestration" / "active"
        migrated += copy_tree_markdown(handoff_source, handoff_target)
    cmd_index(args)
    project_root = Path(getattr(args, "project_root", "") or destination.parent.parent).resolve()
    upsert_registry_project(args.project, project_root, args, name=args.project, sources=[str(project_root)])
    print(f"migrated {migrated} markdown files")


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


def cmd_query(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    db_path = root / "indexes" / "knowledge.sqlite"
    if not db_path.exists():
        cmd_index(args)
    lifecycles = sorted(target_lifecycles(args.target, args.include_background))
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
        for row in conn.execute(sql, [args.query, *lifecycles, args.limit]):
            result = dict(row)
            result["retrieval_role"] = retrieval_role(result, args.target)
            print(json.dumps(result, ensure_ascii=False))
    finally:
        conn.close()


def candidate_v3_classification(path: Path, root: Path, fm: dict[str, object]) -> dict[str, object]:
    rel = path.relative_to(root).as_posix()
    perspective = str(fm.get("perspective", "")).strip("/")
    first = perspective.split("/", 1)[0] if perspective else ""
    lifecycle = lifecycle_from_perspective(perspective) if is_v3_perspective(perspective) else "development_design"
    target_leaf = perspective.split("/", 1)[1] if is_v3_perspective(perspective) else perspective
    target_perspective = perspective if is_v3_perspective(perspective) else f"{lifecycle_to_path_segment(lifecycle)}/{target_leaf or 'architecture/decisions'}"
    status = str(fm.get("status", "draft"))
    if status not in DEFAULT_STATUSES:
        status = "draft"
    if first in LEGACY_PERSPECTIVES or not perspective:
        action = "manual_classification_required"
        confidence = "low"
    elif is_v3_perspective(perspective):
        action = "keep"
        confidence = "high"
    else:
        action = "move"
        confidence = "medium"
    return {
        "old_path": rel,
        "title": fm.get("title", path.stem),
        "old_perspective": perspective,
        "candidate_lifecycle_stage": lifecycle,
        "candidate_perspective": target_perspective,
        "candidate_status": status,
        "confidence": confidence,
        "reason": "dry-run v3 classification; mixed lifecycle content still requires human review",
        "action": action,
    }


def cmd_migrate_v3(args: argparse.Namespace) -> None:
    root = project_dir(args.project, args)
    migration_root = root / "migration"
    migration_root.mkdir(parents=True, exist_ok=True)
    records = []
    for path in markdown_files(root):
        if not path.relative_to(root).as_posix().startswith("notes/"):
            continue
        fm, _ = read_front_matter(path)
        if not fm:
            continue
        records.append(candidate_v3_classification(path, root, fm))
    target = migration_root / "v3-inventory.jsonl"
    target.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + ("\n" if records else ""), encoding="utf-8")
    print(f"wrote {len(records)} inventory records to {target}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    def add_resolution_args(command: argparse.ArgumentParser) -> None:
        command.add_argument("--project-root")
        command.add_argument("--knowledge-root")
        command.add_argument("--cwd")
        command.add_argument("--registry-file")

    init = sub.add_parser("init")
    init.add_argument("--project", required=True)
    init.add_argument("--source")
    add_resolution_args(init)
    init.set_defaults(func=cmd_init)
    resolve = sub.add_parser("resolve")
    add_resolution_args(resolve)
    resolve.set_defaults(func=cmd_resolve)
    write_note = sub.add_parser("write-note")
    write_note.add_argument("--project", required=True)
    write_note.add_argument("--perspective", required=True)
    write_note.add_argument("--title", required=True)
    write_note.add_argument("--content-file", required=True)
    write_note.add_argument("--lifecycle-stage")
    write_note.add_argument("--source-type")
    add_resolution_args(write_note)
    write_note.set_defaults(func=cmd_write_note)
    index = sub.add_parser("index")
    index.add_argument("--project", required=True)
    add_resolution_args(index)
    index.set_defaults(func=cmd_index)
    query = sub.add_parser("query")
    query.add_argument("--project", required=True)
    query.add_argument("--target", required=True, choices=["implementation_spec", "implementation_plan", "execution", "customer_spec", "bidding", "deployment", "operation"])
    query.add_argument("--query", required=True)
    query.add_argument("--mode", default="authority")
    query.add_argument("--limit", type=int, default=20)
    query.add_argument("--include-background", action="store_true")
    add_resolution_args(query)
    query.set_defaults(func=cmd_query)
    index_oq = sub.add_parser("index-open-questions")
    index_oq.add_argument("--project", required=True)
    add_resolution_args(index_oq)
    index_oq.set_defaults(func=cmd_index_open_questions)
    git = sub.add_parser("git")
    git.add_argument("--project", required=True)
    add_resolution_args(git)
    git.add_argument("git_args", nargs=argparse.REMAINDER)
    git.set_defaults(func=cmd_git)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--project", required=True)
    add_resolution_args(doctor)
    doctor.set_defaults(func=cmd_doctor)
    output = sub.add_parser("output")
    output.add_argument("--project", required=True)
    output.add_argument("--title", required=True)
    output.add_argument("--content-file", required=True)
    output.add_argument("--output-file")
    add_resolution_args(output)
    output.set_defaults(func=cmd_output)
    breakdown = sub.add_parser("breakdown-design")
    breakdown.add_argument("--project", required=True)
    breakdown.add_argument("--input", required=True)
    breakdown.add_argument("--parts")
    breakdown.add_argument("--language", default="same-as-source")
    add_resolution_args(breakdown)
    breakdown.set_defaults(func=cmd_breakdown_design)
    add_question = sub.add_parser("add-question")
    add_question.add_argument("--project", required=True)
    add_question.add_argument("--perspective", required=True)
    add_question.add_argument("--title", required=True)
    add_question.add_argument("--content-file", required=True)
    add_question.add_argument("--trigger-terms", default="")
    add_question.add_argument("--source-note-ids", default="")
    add_resolution_args(add_question)
    add_question.set_defaults(func=cmd_add_question)
    list_questions = sub.add_parser("list-questions")
    list_questions.add_argument("--project", required=True)
    list_questions.add_argument("--status")
    list_questions.add_argument("--perspective")
    add_resolution_args(list_questions)
    list_questions.set_defaults(func=cmd_list_questions)
    match_questions = sub.add_parser("match-questions")
    match_questions.add_argument("--project", required=True)
    match_questions.add_argument("--text-file")
    match_questions.add_argument("--text")
    match_questions.add_argument("--include-resolved", action="store_true")
    add_resolution_args(match_questions)
    match_questions.set_defaults(func=cmd_match_questions)
    resolve_question = sub.add_parser("resolve-question")
    resolve_question.add_argument("--project", required=True)
    resolve_question.add_argument("--id", required=True)
    resolve_question.add_argument("--resolution-file", required=True)
    resolve_question.add_argument("--resolved-by-note")
    add_resolution_args(resolve_question)
    resolve_question.set_defaults(func=cmd_resolve_question)
    migrate = sub.add_parser("migrate-legacy")
    migrate.add_argument("--project", required=True)
    migrate.add_argument("--legacy-root")
    add_resolution_args(migrate)
    migrate.set_defaults(func=cmd_migrate_legacy)
    migrate_v3 = sub.add_parser("migrate-v3")
    migrate_v3.add_argument("--project", required=True)
    migrate_v3.add_argument("--dry-run", action="store_true")
    add_resolution_args(migrate_v3)
    migrate_v3.set_defaults(func=cmd_migrate_v3)
    register = sub.add_parser("register-project")
    register.add_argument("--project", required=True)
    register.add_argument("--project-root", required=True)
    register.add_argument("--name")
    register.add_argument("--alias", action="append")
    register.add_argument("--source", action="append")
    register.add_argument("--registry-file")
    register.set_defaults(func=cmd_register_project)
    unregister = sub.add_parser("unregister-project")
    unregister.add_argument("--project", required=True)
    unregister.add_argument("--registry-file")
    unregister.set_defaults(func=cmd_unregister_project)
    list_projects = sub.add_parser("list-projects")
    list_projects.add_argument("--registry-file")
    list_projects.set_defaults(func=cmd_list_projects)
    registry_doctor = sub.add_parser("registry-doctor")
    registry_doctor.add_argument("--registry-file")
    registry_doctor.set_defaults(func=cmd_registry_doctor)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
