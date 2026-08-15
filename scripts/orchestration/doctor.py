import json

from core import *
from handoffs import index_handoffs
from plans import index_plans
from specs import load_index


FORBIDDEN_EXECUTOR_RESULT_FIELDS = {
    "suggested_durable_conclusions",
    "durable_candidate_facts",
    "recommended_orchestration_review",
    "recommended_next_actions",
    "delegation",
    "deviations",
    "strategy_advice",
    "knowledge_persistence",
}


def check_contract_terms(issues: list[str], path: Path, label: str, required_terms: list[str]) -> None:
    if not path.exists():
        issues.append(f"missing {label}: {path}")
        return
    text = path.read_text(encoding="utf-8")
    for term in required_terms:
        if term not in text:
            issues.append(f"{label} missing workflow contract term: {term}")


def check_eval_shape(issues: list[str], path: Path) -> None:
    if not path.exists():
        issues.append(f"missing orchestration evals: {path}")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"invalid orchestration eval JSON: {exc}")
        return
    cases = data.get("evals")
    if not isinstance(cases, list):
        issues.append("orchestration eval JSON missing evals list")
        return
    seen_ids: set[object] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            issues.append(f"orchestration eval entry {index} is not an object")
            continue
        missing = [key for key in ("id", "prompt", "expected_output", "files") if key not in case]
        if missing:
            issues.append(f"orchestration eval entry {index} missing fields: {', '.join(missing)}")
        case_id = case.get("id")
        if not isinstance(case_id, (int, str)):
            issues.append(f"orchestration eval entry {index} has invalid id")
            continue
        if case_id in seen_ids:
            issues.append(f"duplicate orchestration eval id: {case_id}")
        seen_ids.add(case_id)


def check_forbidden_active_dependencies(issues: list[str], paths: list[Path]) -> None:
    forbidden_runtime_file = "HAB" "ITS.md"
    positive_role_context_terms = (
        "## Role Context",
        "Use `wb-select-role-context`",
        "Invoke `wb-select-role-context`",
        "Required Skill: `wb-select-role-context`",
    )
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if forbidden_runtime_file in text:
            issues.append(f"active orchestration contract depends on forbidden runtime file: {path}")
        for term in positive_role_context_terms:
            if term in text:
                issues.append(f"active orchestration contract reintroduces role-context dependency: {path}")


def check_active_handoff_contract(issues: list[str], root: Path) -> None:
    active_orchestration = root / "handoff" / "orchestration" / "active"
    if active_orchestration.exists():
        for path in active_orchestration.iterdir():
            if path.is_file():
                issues.append(f"active orchestration handoff is retired: {path.relative_to(root)}")

    active_executor = root / "handoff" / "executor" / "active"
    for pattern in ("*.yaml", "*.yml"):
        for path in active_executor.glob(pattern):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line or line[0].isspace() or ":" not in line:
                    continue
                field = line.split(":", 1)[0]
                if field in FORBIDDEN_EXECUTOR_RESULT_FIELDS:
                    issues.append(
                        f"active executor-result handoff contains forbidden field {field}: "
                        f"{path.relative_to(root)}"
                    )


def index_row_identity(index_scope: str, row: dict[str, object]) -> tuple[object, ...]:
    row_type = str(row.get("type", index_scope))
    row_id = str(row.get("id", ""))
    if index_scope == "plan" and row_type == "phase":
        return (row_type, row.get("plan_id"), row_id)
    if index_scope == "plan" and row_type == "task":
        return (row_type, row.get("plan_id"), row.get("phase_id"), row_id)
    if index_scope == "handoff":
        return (
            row_type,
            row.get("related_plan"),
            row.get("related_phase"),
            row.get("related_task"),
            row_id,
        )
    return (row_type, row_id)


def cmd_doctor(args: argparse.Namespace) -> None:
    init_dirs(args)
    issues = []
    root = orchestration_root(args)
    bundle_root = Path(__file__).resolve().parents[2]
    for required in ["spec/active", "spec/archived", "spec/index.jsonl", "plan/active", "plan/archived", "plan/index.jsonl", "handoff/orchestration/archived", "handoff/executor/active", "handoff/executor/archived", "handoff/index.jsonl", "docs"]:
        if not (root / required).exists():
            issues.append(f"missing {required}")
    for index_scope, index in [
        ("spec", "spec/index.jsonl"),
        ("plan", "plan/index.jsonl"),
        ("handoff", "handoff/index.jsonl"),
    ]:
        seen: set[tuple[object, ...]] = set()
        for row in load_index(root / index):
            identity = index_row_identity(index_scope, row)
            if identity in seen:
                issues.append(f"duplicate {index_scope} identity {identity}")
            seen.add(identity)
            path = project_root(args) / str(row.get("path", ""))
            if not is_relative_to(path, root):
                issues.append(f"index path escapes orchestration root: {row}")
    active_artifact_roots = [
        root / "spec" / "active",
        root / "plan" / "active",
        root / "handoff" / "executor" / "active",
        root / "docs",
    ]
    for active_root in active_artifact_roots:
        for path in active_root.glob("**/*.md"):
            if ".work-bundle/knowledge" in path.resolve().as_posix():
                issues.append(f"artifact under knowledge root: {path}")
    for path in (root / "spec" / "active").glob("**/*.md"):
        if artifact_mentions_retrieval_without_roles(path):
            issues.append(f"retrieval artifact lacks role labels: {path.relative_to(root)}")
    check_active_handoff_contract(issues, root)
    skill_root = bundle_root / "skills"
    orchestration_evals = bundle_root / "references" / "evals" / "orchestration" / "evals.json"
    check_eval_shape(issues, orchestration_evals)
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
            if "no-retrieval stage" not in text and "must not invoke retrieval" not in text:
                issues.append("orch-execute-plan lacks explicit no-retrieval rule")
        elif skill_name == "orch-create-specification":
            required_terms = [
                "polarity-neutral and stage/perspective/status-neutral query anchors",
                "classification and output-grouping intent, not a discovery-stage lifecycle filter",
                "supporting, opposing, constraining, unresolved/open-question",
                "execution does not require `.work-bundle/knowledge/` reads",
            ]
            for required in required_terms:
                if required not in text:
                    issues.append(
                        "orch-create-specification missing no-stage-gate contract term: "
                        f"{required}"
                    )
        elif policy not in text and "Knowledge Gateway" in text:
            issues.append(f"orch skill does not mention mapped retrieval policy {policy}: {skill_name}")
    ks_what_is_helpful_skill = skill_root / "ks-what-is-helpful" / "SKILL.md"
    if not ks_what_is_helpful_skill.exists():
        issues.append("missing ks-what-is-helpful skill file")
    else:
        text = ks_what_is_helpful_skill.read_text(encoding="utf-8")
        for required in [
            "Gateway mode",
            "ks.py query",
            "policy_hint",
            "mechanical candidate and trace evidence",
            "semantic relevance, authority, polarity, conflict, materiality",
            "authority",
            "candidate",
            "background",
            "blocked",
        ]:
            if required not in text:
                issues.append(f"ks-what-is-helpful missing gateway contract term: {required}")
    for path in [bundle_root / "references" / "assets" / "keep-summarizing" / "workflow.md"]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if "notes/<leaf-perspective>" in text or "status: archived" in text:
                issues.append(f"keep-summarizing doc advertises legacy path/status: {path.relative_to(bundle_root)}")
    workflow_contracts = [
        (
            bundle_root / "references" / "assets" / "orchestration" / "workflow.md",
            "orchestration workflow",
            [
                "Disposable task briefs, review packages, and lightweight development plans",
                "build-task-brief",
                "independent dev-code-review",
                "A task becomes `Completed` only when",
                "Final workflow audit",
            ],
        ),
        (
            bundle_root / "references" / "assets" / "orchestration" / "contract" / "handoff-executor-result-v1.md",
            "executor-result handoff contract",
            [
                "default_format: yaml",
                "Required By Applicability",
                "Forbidden Executor-Result Fields",
                "task_fit_check:",
                "delegation_evidence:",
                "reason: null | no-index | sync-failed | not-source-code | blocked",
            ],
        ),
        (
            bundle_root / "scripts" / "orchestration" / "handoffs.py",
            "handoff helper",
            [
                'HANDOFF_EXTENSIONS = (".md", ".yaml", ".yml")',
                "Active orchestration handoff creation is retired",
                '"yaml" if args.type == "executor-result" else "markdown"',
            ],
        ),
        (
            bundle_root / "references" / "assets" / "keep-summarizing" / "workflow.md",
            "keep-summarizing workflow",
            [
                "neutral hybrid candidate discovery followed by explicit authority, candidate, background, blocked, polarity, materiality, and blocker classification",
            ],
        ),
        (
            skill_root / "orch-create-specification" / "SKILL.md",
            "orch-create-specification skill",
            [
                "authority, candidate, background, or blocked",
                "polarity-neutral and stage/perspective/status-neutral query anchors",
                "classification and output-grouping intent",
                "semantic_loop:",
                "Quality gate: verified|blocked",
            ],
        ),
        (
            bundle_root / "rules" / "orchestration" / "orch-knowledge-gateway.md",
            "orch-knowledge-gateway rule",
            [
                "Discover relevant candidates across allowed lifecycle partitions",
                "classification and output-grouping intent",
                "not as a discovery-stage lifecycle filter",
                "Treat a directive retrieval policy such as `implementation_spec` as a stage-gated discovery filter",
                "retrieval policy did not stage-gate candidate discovery",
                "future knowledge-base lookup",
            ],
        ),
        (
            bundle_root / "references" / "assets" / "orchestration" / "contract" / "specification-v1.md",
            "specification contract",
            [
                "neutral and cross-stage",
                "classification/output intent rather than a discovery-stage filter",
                "supporting, opposing, constraining, unresolved/open-question",
                "downstream planning and execution do not need to read `.work-bundle/knowledge/`",
            ],
        ),
        (
            bundle_root / "scripts" / "orchestration" / "core.py",
            "orchestration core policy helper",
            [
                "Directive policies describe classification/output intent only",
                '"discovery": "neutral-cross-stage"',
                '"usage": "classification-output-intent"',
            ],
        ),
        (
            skill_root / "orch-create-implementation-plan" / "SKILL.md",
            "orch-create-implementation-plan skill",
            ["source-ID coverage", "dev-semantic-convergence", "context_mode: compiled-brief"],
        ),
        (
            skill_root / "orch-execute-plan" / "SKILL.md",
            "orch-execute-plan skill",
            [
                "Before compilation, capability selection, delegation, or edits",
                "every target repository",
                "build-task-brief",
                "validate-executor-result",
                "reviewer_independent: false",
            ],
        ),
        (
            skill_root / "orch-execute-plan" / "SKILL.md",
            "orch-execute-plan skill",
            ["Execution Constraints (skill-owned)", "no-retrieval stage", "record `no-index`"],
        ),
        (
            ks_what_is_helpful_skill,
            "ks-what-is-helpful skill",
            [
                "A retrieval policy is caller intent for later classification, not a discovery-stage filter",
                "Classify and rank",
                "Scripts must not decide semantic relevance, authority, polarity, conflict, materiality",
                "Do not convert non-authority results into requirements, tasks, decisions, or review conclusions",
            ],
        ),
        (
            bundle_root / "rules" / "agent-codegraph-first.md",
            "CodeGraph-first rule",
            ["targeted repository root contains `.codegraph/`", "Do not skip CodeGraph silently", "record the concrete fallback reason"],
        ),
        (
            orchestration_evals,
            "orchestration evals",
            [
                "material candidate knowledge conflicts with the user purpose",
                "outside the implementation_spec lifecycle",
                "classification and output-grouping intent",
                "does not require downstream knowledge-base lookup",
                "quality gate is verified",
                "accepted independent task review",
                "task-review verdict",
                "target repository has no .codegraph directory",
                "sparse YAML",
                "active orchestration handoff",
            ],
        ),
        (
            skill_root / "orch-review-plan" / "SKILL.md",
            "orch-review-plan skill",
            [
                "workflow audit and deterministic finalizer",
                "compiled Truth Basis",
                "Knowledge Base Update disposition is `completed` or `not-needed`",
                "approved `ks-*` return evidence",
                "Do not broadly inspect source",
                "Do not create a repair specification for every failed gate",
                "orch-review-completion",
            ],
        ),
    ]
    for path, label, required_terms in workflow_contracts:
        check_contract_terms(issues, path, label, required_terms)
    check_forbidden_active_dependencies(
        issues,
        [
            skill_root / "orch-create-specification" / "SKILL.md",
            skill_root / "orch-create-implementation-plan" / "SKILL.md",
            skill_root / "orch-execute-plan" / "SKILL.md",
            bundle_root / "references" / "assets" / "orchestration" / "workflow.md",
            bundle_root / "rules" / "agent-codegraph-first.md",
        ],
    )
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print("ok")
