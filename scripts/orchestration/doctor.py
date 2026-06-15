from core import *
from handoffs import index_handoffs
from plans import index_plans
from specs import load_index


def check_contract_terms(issues: list[str], path: Path, label: str, required_terms: list[str]) -> None:
    if not path.exists():
        issues.append(f"missing {label}: {path}")
        return
    text = path.read_text(encoding="utf-8")
    for term in required_terms:
        if term not in text:
            issues.append(f"{label} missing workflow contract term: {term}")


def cmd_doctor(args: argparse.Namespace) -> None:
    init_dirs(args)
    issues = []
    root = orchestration_root(args)
    bundle_root = Path(__file__).resolve().parents[2]
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
    skill_root = bundle_root / "skills"
    orch_skill_policy_map = {
        "orch-create-specification": "implementation_spec",
        "orch-create-implementation-plan": "implementation_plan",
        "orch-create-document": "customer_spec",
        "orch-create-handoff": "implementation_plan",
        "orch-review-plan": "implementation_plan",
        "orch-execute-plan": "execution",
    }
    for skill_name, policy in orch_skill_policy_map.items():
        path = skill_root / skill_name / "SKILL.md"
        if not path.exists():
            issues.append(f"missing orch skill file for policy check: {skill_name}")
            continue
        text = path.read_text(encoding="utf-8")
        if skill_name == "orch-execute-plan":
            if "must not run v3 retrieval" not in text and "must not invoke retrieval" not in text:
                issues.append("orch-execute-plan lacks explicit no-retrieval rule")
        elif policy not in text and "Knowledge Gateway" in text:
            issues.append(f"orch skill does not mention mapped retrieval policy {policy}: {skill_name}")
    ks_directive_root = bundle_root / "references" / "directives" / "keep-summarizing"
    what_is_helpful = ks_directive_root / "what-is-helpful.md"
    if not what_is_helpful.exists():
        issues.append("missing keep-summarizing what-is-helpful directive")
    else:
        text = what_is_helpful.read_text(encoding="utf-8")
        for required in ["Gateway mode", "ks.py query", "retrieval_role", "authority", "candidate", "background", "blocked"]:
            if required not in text:
                issues.append(f"what-is-helpful missing gateway contract term: {required}")
    for path in [bundle_root / "skills" / "ks-what-is-helpful" / "migration.md", bundle_root / "references" / "assets" / "keep-summarizing" / "workflow.md"]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if "notes/<leaf-perspective>" in text or "status: archived" in text:
                issues.append(f"keep-summarizing doc advertises legacy path/status: {path.relative_to(bundle_root)}")
    workflow_contracts = [
        (
            bundle_root / "references" / "assets" / "orchestration" / "workflow.md",
            "orchestration workflow",
            [
                "Before execution selection, capability checks, delegation, or implementation changes",
                "keeps archive blocked if delegation is unavailable or evidence is incomplete",
            ],
        ),
        (
            bundle_root / "references" / "assets" / "keep-summarizing" / "workflow.md",
            "keep-summarizing workflow",
            ["full candidate discovery followed by explicit authority, candidate, background, and blocked classification"],
        ),
        (
            skill_root / "orch-execute-plan" / "SKILL.md",
            "orch-execute-plan skill",
            ["## Repository Preflight", "every target source repository", "Block when no target repository resolves or any target reports `dirty`"],
        ),
        (
            skill_root / "orch-execute-plan" / "SKILL.md",
            "orch-execute-plan skill",
            ["Execution Constraints (skill-owned)", "clean-worktree preflight"],
        ),
        (
            what_is_helpful,
            "what-is-helpful directive",
            ["discover relevant candidates across every allowed lifecycle partition", "Classify only after full candidate discovery", "`authority` may shape downstream artifacts"],
        ),
        (
            bundle_root / "skills" / "ks-what-is-helpful" / "migration.md",
            "ks-what-is-helpful skill",
            ["ks-note-state-authority", "Discover relevant candidates across all allowed lifecycle partitions before lifecycle/status authority classification"],
        ),
        (
            skill_root / "orch-review-plan" / "SKILL.md",
            "orch-review-plan skill",
            ["## Delegate-Return-Resume Protocol", "delegate mixed implementation, validation, handoff, and review evidence to `ks-extract-valuable-points`", "do not archive until all other review checks pass and disposition is `completed` or `not-needed`"],
        ),
        (
            skill_root / "orch-review-plan" / "SKILL.md",
            "orch-review-plan skill",
            ["orch-review-completion", "ks-extract-valuable-points", "may invoke, schedule, or hand off to an approved `ks-*` owner"],
        ),
    ]
    for path, label, required_terms in workflow_contracts:
        check_contract_terms(issues, path, label, required_terms)
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print("ok")
