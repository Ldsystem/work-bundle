from core import *
from core import _anchor_context
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
    if getattr(args, "workspace_root", None):
        context = _anchor_context(workspace_root=args.workspace_root)
    elif getattr(args, "project_root", None):
        context = _anchor_context(project_root=args.project_root, cwd=args.project_root)
    else:
        context = _anchor_context(cwd=cwd)
    root = work_bundle_knowledge_root(context.workspace_root)
    print(read_project_slug(root, context.workspace_root.name))
