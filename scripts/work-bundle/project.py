from __future__ import annotations

from core import *


def _slug_from_root(project_root: Path, name: str | None = None) -> str:
    raw = name or project_root.name or "project"
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw.strip().lower()).strip("-")
    return slug or "project"


def _bootstrap_value(key: str, default: str) -> str:
    config_root = work_bundle_config_root()
    bootstrap = compact_yaml_map(read(config_root / GLOBAL_BOOTSTRAP_FILE_NAME))
    value = bootstrap.get(key, default)
    return value.replace("$work_bundle_config_root", str(config_root))


def project_registry_path() -> Path:
    return Path(_bootstrap_value("project_registry", "$work_bundle_config_root/registry/projects.yaml")).expanduser().resolve()


def _project_blocks(path: Path) -> list[dict[str, object]]:
    text = read(path)
    projects: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_list: str | None = None
    current_repo: dict[str, object] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped == "projects:":
            continue
        if line.startswith("  - "):
            if current is not None:
                projects.append(current)
            current = {}
            current_list = None
            current_repo = None
            key, value = stripped[2:].split(":", 1)
            current[key.strip()] = value.strip().strip('"')
            continue
        if current is None:
            continue
        if stripped.startswith("- ") and current_list:
            item = stripped[2:].strip()
            if current_list == "aliases":
                current.setdefault("aliases", []).append(item)
            elif current_list == "source_repositories":
                current_repo = {}
                current.setdefault("source_repositories", []).append(current_repo)
                if ":" in item:
                    key, value = item.split(":", 1)
                    current_repo[key.strip()] = value.strip().strip('"')
            continue
        if line.startswith("    ") and not line.startswith("      "):
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_list = None
            current_repo = None
            if value == "":
                if key in {"aliases", "source_repositories"}:
                    current[key] = []
                    current_list = key
                else:
                    current[key] = {}
            elif value == "[]":
                current[key] = []
            else:
                current[key] = value.strip('"')
            continue
        if line.startswith("      ") and current_repo is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip().strip('"')
            if value in {"true", "false"}:
                current_repo[key.strip()] = value == "true"
            else:
                current_repo[key.strip()] = value
    if current is not None:
        projects.append(current)
    return projects


def _render_projects(projects: list[dict[str, object]]) -> str:
    lines = ["projects:"]
    for project in sorted(projects, key=lambda item: str(item.get("slug", ""))):
        lines.append(f"  - slug: {project.get('slug', '')}")
        lines.append(f"    name: {project.get('name', project.get('slug', ''))}")
        lines.append(f"    work_bundle_root: {project.get('work_bundle_root', '')}")
        lines.append(f"    knowledge_root: {project.get('knowledge_root', '')}")
        aliases = project.get("aliases") if isinstance(project.get("aliases"), list) else []
        if aliases:
            lines.append("    aliases:")
            for alias in aliases:
                lines.append(f"      - {alias}")
        else:
            lines.append("    aliases: []")
        sources = project.get("source_repositories") if isinstance(project.get("source_repositories"), list) else []
        lines.append("    source_repositories:")
        for index, source in enumerate(sources or [{"path": project.get("project_root", ""), "work_dir": True, "remote": ""}]):
            if not isinstance(source, dict):
                continue
            lines.append(f"      - path: {source.get('path', '')}")
            lines.append(f"        work_dir: {str(bool(source.get('work_dir', index == 0))).lower()}")
            lines.append(f"        remote: {source.get('remote', '')}")
        lines.append(f"    status: {project.get('status', 'active')}")
        lines.append(f"    updated_at: {project.get('updated_at', utc_now_rfc3339()[:10])}")
    return "\n".join(lines) + "\n"


def registry_entry(project_root: Path, name: str | None = None, aliases: list[str] | None = None) -> dict[str, object]:
    slug = _slug_from_root(project_root, name)
    return {
        "slug": slug,
        "name": name or slug,
        "work_bundle_root": str(project_root / ".work-bundle"),
        "knowledge_root": str(project_root / ".work-bundle" / "knowledge"),
        "aliases": aliases or [],
        "source_repositories": [{"path": str(project_root), "work_dir": True, "remote": ""}],
        "status": "active",
        "updated_at": utc_now_rfc3339()[:10],
    }


def upsert_project_registry(project_root: Path, name: str | None = None, aliases: list[str] | None = None) -> tuple[dict[str, object], bool, Path]:
    path = project_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    projects = _project_blocks(path)
    entry = registry_entry(project_root, name, aliases)
    changed = False
    replaced = False
    next_projects: list[dict[str, object]] = []
    for project in projects:
        sources = project.get("source_repositories")
        source_paths = [
            str(Path(str(source.get("path", ""))).expanduser().resolve())
            for source in sources
            if isinstance(sources, list) for source in sources if isinstance(source, dict) and source.get("path")
        ] if isinstance(sources, list) else []
        same_slug = project.get("slug") == entry["slug"]
        same_root = str(project_root) in source_paths or project.get("work_bundle_root") == entry["work_bundle_root"]
        if same_slug or same_root:
            next_projects.append(entry)
            replaced = True
            changed = changed or project != entry
        else:
            next_projects.append(project)
    if not replaced:
        next_projects.append(entry)
        changed = True
    rendered = _render_projects(next_projects)
    if read(path) != rendered:
        write(path, rendered)
        changed = True
    return entry, changed, path


def find_registry_entry(project_root: Path) -> tuple[dict[str, object] | None, Path]:
    path = project_registry_path()
    target = str(project_root.resolve())
    for project in _project_blocks(path):
        if project.get("work_bundle_root") == str(project_root / ".work-bundle"):
            return project, path
        sources = project.get("source_repositories")
        if isinstance(sources, list):
            for source in sources:
                if isinstance(source, dict) and source.get("path"):
                    if str(Path(str(source["path"])).expanduser().resolve()) == target:
                        return project, path
    return None, path


def list_project_registry() -> tuple[list[dict[str, object]], Path]:
    path = project_registry_path()
    return _project_blocks(path), path


def remove_project_registry(project: str) -> tuple[bool, Path]:
    path = project_registry_path()
    projects = _project_blocks(path)
    kept: list[dict[str, object]] = []
    removed = False
    for entry in projects:
        aliases = entry.get("aliases")
        alias_match = isinstance(aliases, list) and project in aliases
        if entry.get("slug") == project or alias_match:
            removed = True
            continue
        kept.append(entry)
    if removed:
        write(path, _render_projects(kept))
    return removed, path


def project_registry_issues() -> list[str]:
    projects, path = list_project_registry()
    if not path.exists():
        return [f"missing registry file: {path}"]
    issues: list[str] = []
    seen: set[str] = set()
    for entry in projects:
        slug = str(entry.get("slug", ""))
        if not slug:
            issues.append("project entry missing slug")
            continue
        if slug in seen:
            issues.append(f"duplicate slug {slug}")
        seen.add(slug)
        for key in ["work_bundle_root", "knowledge_root"]:
            if not entry.get(key):
                issues.append(f"missing {key}: {slug}")
    return issues


def cmd_init_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py init-project")
    parser.add_argument("project_root")
    parser.add_argument("--name")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-work-bundle-git", action="store_true")
    parser.add_argument("--create-project-skill-override", action="store_true")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    changed: list[str] | str = "none"
    if not parsed.dry_run:
        changed = apply_project(
            project_root,
            init_git=not parsed.disable_work_bundle_git,
            create_override=parsed.create_project_skill_override,
        )
        entry, registry_changed, registry = upsert_project_registry(project_root, parsed.name)
        if registry_changed and isinstance(changed, list):
            changed.append(str(registry))
    else:
        entry = registry_entry(project_root, parsed.name)
        registry = project_registry_path()
    data = inspect_project(project_root)
    failures = project_failures(data, strict=not parsed.dry_run, include_roles=False)
    data.update({
        "command": "init-project",
        "registry_path": str(registry),
        "registry_entry": entry,
        "status": "passed" if not failures else "issues-found",
        "failures": failures,
    })
    if parsed.dry_run:
        data["dry_run"] = True
    else:
        data["changed_files"] = sorted(set(changed if isinstance(changed, list) else []))
    out(data)
    return 0 if not failures else 1


def cmd_register_project_command(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py register-project")
    parser.add_argument("project_root")
    parser.add_argument("--name")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    entry, changed, registry = upsert_project_registry(project_root, parsed.name)
    out({"command": "register-project", "status": "updated" if changed else "skipped", "registry_path": str(registry), "project": entry})
    return 0


def cmd_show_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py show-project")
    parser.add_argument("--project-root", default=".")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    data = inspect_project(project_root)
    entry, registry = find_registry_entry(project_root)
    failures = project_failures(data, strict=False, include_roles=False)
    data.update({
        "command": "show-project",
        "registry_path": str(registry),
        "registry_status": "registered" if entry else "not-registered",
        "registry_entry": entry,
        "status": "passed" if not failures else "issues-found",
        "failures": failures,
    })
    out(data)
    return 0


def cmd_validate_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py validate-project")
    parser.add_argument("project_root")
    parser.add_argument("--dry-run", action="store_true")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    data = inspect_project(project_root)
    entry, registry = find_registry_entry(project_root)
    failures = project_failures(data, strict=True, include_roles=False)
    if entry is None:
        failures.append("project_not_registered")
    data.update({
        "command": "validate-project",
        "registry_path": str(registry),
        "registry_status": "registered" if entry else "not-registered",
        "registry_entry": entry,
        "status": "passed" if not failures else "issues-found",
        "failures": failures,
    })
    out(data)
    return 0 if not failures else 1


def cmd_migrate_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py migrate-project")
    parser.add_argument("project_root")
    parser.add_argument("--name")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    before = inspect_project(project_root)
    changed = apply_project(project_root, init_git=False)
    entry, registry_changed, registry = upsert_project_registry(project_root, parsed.name)
    if registry_changed:
        changed.append(str(registry))
    after = inspect_project(project_root)
    failures = project_failures(after, strict=True, include_roles=False)
    report = project_root / ".work-bundle" / "orchestration" / "docs" / f"migration-report-{utc_now_rfc3339()[:10]}.md"
    report_text = "\n".join([
        "# Work-Bundle Project Migration Report",
        "",
        f"- project_root: {project_root}",
        f"- status: {'passed' if not failures else 'issues-found'}",
        f"- before_status: {'passed' if not project_failures(before, strict=False, include_roles=False) else 'issues-found'}",
        f"- changed_files: {len(set(changed))}",
        "",
    ])
    if write(report, report_text, overwrite=False):
        changed.append(str(report))
    out({
        "command": "migrate-project",
        "status": "passed" if not failures else "issues-found",
        "failures": failures,
        "changed_files": sorted(set(changed)),
        "migration_report": str(report),
        "registry_path": str(registry),
        "registry_entry": entry,
        "before_status": "passed" if not project_failures(before, strict=False, include_roles=False) else "issues-found",
    })
    return 0 if not failures else 1


def cmd_project(args: list[str], apply: bool = False, inspect_only: bool = False, repo_model: bool = False) -> int:
    if apply:
        return cmd_init_project(args)
    if inspect_only:
        return cmd_show_project(["--project-root", args[0]] if args else [])
    return cmd_validate_project(args)
