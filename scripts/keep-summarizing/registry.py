from core import *
import importlib.util
import sys


def _load_work_bundle_project_module():
    module_path = Path(__file__).resolve().parents[1] / "work-bundle" / "project.py"
    module_dir = str(module_path.parent)
    old_core = sys.modules.pop("core", None)
    sys.path.insert(0, module_dir)
    try:
        spec = importlib.util.spec_from_file_location("work_bundle_project_compat", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load work-bundle project module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if sys.path and sys.path[0] == module_dir:
            sys.path.pop(0)
        if old_core is not None:
            sys.modules["core"] = old_core

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
    module = _load_work_bundle_project_module()
    entry, _, _ = module.upsert_project_registry(project_root.resolve(), name or project, aliases or [])
    return entry


def cmd_register_project(args: argparse.Namespace) -> None:
    project_root = Path(args.project_root).expanduser().resolve()
    aliases = args.alias or []
    entry = upsert_registry_project(args.project, project_root, args, name=args.name, aliases=aliases, sources=args.source)
    print(json.dumps(entry, ensure_ascii=False))


def cmd_unregister_project(args: argparse.Namespace) -> None:
    module = _load_work_bundle_project_module()
    removed, _ = module.remove_project_registry(args.project)
    print("removed" if removed else "not found")


def cmd_list_projects(args: argparse.Namespace) -> None:
    module = _load_work_bundle_project_module()
    projects, _ = module.list_project_registry()
    for entry in projects:
        print(json.dumps(entry, ensure_ascii=False))


def registry_issues(args: argparse.Namespace) -> list[str]:
    module = _load_work_bundle_project_module()
    return module.project_registry_issues()


def cmd_registry_doctor(args: argparse.Namespace) -> None:
    issues = registry_issues(args)
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print("ok")
