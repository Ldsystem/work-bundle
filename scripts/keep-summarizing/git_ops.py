from core import *

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

