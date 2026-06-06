from core import *
from indexes import cmd_index
from registry import upsert_registry_project

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

