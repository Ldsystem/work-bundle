from core import *
from handoffs import index_handoffs
from plans import index_plans
from specs import load_index

def cmd_doctor(args: argparse.Namespace) -> None:
    init_dirs(args)
    issues = []
    root = orchestration_root(args)
    for required in ["spec/active", "spec/archived", "spec/index.jsonl", "plan/active", "plan/archived", "plan/index.jsonl", "handoff/orchestration/active", "handoff/orchestration/archived", "handoff/executor/active", "handoff/executor/archived", "handoff/index.jsonl", "docs"]:
        if not (root / required).exists():
            issues.append(f"missing {required}")
    seen = set()
    for index in ["spec/index.jsonl", "plan/index.jsonl", "handoff/index.jsonl"]:
        for row in load_index(root / index):
            rid = str(row.get("id", ""))
            if rid in seen:
                issues.append(f"duplicate id {rid}")
            seen.add(rid)
            path = project_root(args) / str(row.get("path", ""))
            if not is_relative_to(path, root):
                issues.append(f"index path escapes orchestration root: {row}")
    for path in root.glob("**/*.md"):
        if ".work-bundle/knowledge" in path.resolve().as_posix():
            issues.append(f"artifact under knowledge root: {path}")
        if artifact_mentions_retrieval_without_roles(path):
            issues.append(f"retrieval artifact lacks role labels: {path.relative_to(root)}")
    directive_root = Path(__file__).resolve().parents[2] / "references" / "directives"
    knowledge_directives = {"create-specification", "create-implementation-plan", "create-document", "create-handoff", "review-plan", "execute-plan"}
    for directive in knowledge_directives:
        path = directive_root / f"{directive}.md"
        if not path.exists():
            issues.append(f"missing directive file for policy check: {directive}")
            continue
        text = path.read_text(encoding="utf-8")
        if directive == "execute-plan":
            if "must not run v3 retrieval" not in text and "must not invoke retrieval" not in text:
                issues.append("execute-plan lacks explicit no-retrieval rule")
        elif directive not in DIRECTIVE_POLICY_MAP:
            issues.append(f"missing retrieval policy mapping: {directive}")
        elif DIRECTIVE_POLICY_MAP[directive] not in text and "Knowledge Gateway" in text:
            issues.append(f"directive does not mention mapped retrieval policy {DIRECTIVE_POLICY_MAP[directive]}: {directive}")
    ks_root = keep_summarizing_root()
    what_is_helpful = ks_root / "references" / "directives" / "what-is-helpful.md"
    if not what_is_helpful.exists():
        issues.append("missing keep-summarizing what-is-helpful directive")
    else:
        text = what_is_helpful.read_text(encoding="utf-8")
        for required in ["Gateway mode", "ks.py query", "retrieval_role", "authority", "candidate", "background", "blocked"]:
            if required not in text:
                issues.append(f"what-is-helpful missing gateway contract term: {required}")
    for path in [ks_root / "SKILL.md", ks_root / "README.md", ks_root / "references" / "workflow.md"]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if "notes/<leaf-perspective>" in text or "status: archived" in text:
                issues.append(f"keep-summarizing doc advertises legacy path/status: {path.relative_to(ks_root)}")
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print("ok")

