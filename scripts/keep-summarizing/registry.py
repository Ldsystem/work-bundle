from core import *

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

