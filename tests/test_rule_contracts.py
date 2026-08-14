from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_wb(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), *args],
        cwd=cwd or REPO_ROOT,
        env=command_env,
        check=False,
        capture_output=True,
        text=True,
    )


def valid_rule_md(
    rule_id: str,
    *,
    applies_when: list[str] | None = None,
    extra_front_matter: str = "",
) -> str:
    applies = applies_when if applies_when is not None else ["task runs"]
    applies_yaml = "\n".join(f"  - {item}" for item in applies)
    return (
        "---\n"
        f"id: {rule_id}\n"
        "applies_when:\n"
        f"{applies_yaml}\n"
        "enforcement: must\n"
        "load: conditional\n"
        "requires: []\n"
        f"{extra_front_matter}"
        "---\n\n"
        f"# {rule_id}\n\n"
        "## Purpose\n\n- purpose\n\n"
        "## Must\n\n- must\n\n"
        "## Must Not\n\n- must not\n\n"
        "## Validation\n\n- validate\n\n"
        "## On Violation\n\n- stop\n"
    )


def test_validate_current_rules_passes() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "work-bundle"))
    try:
        import rules as rules_module

        rules_root = REPO_ROOT / "rules"
        for path in rules_module.markdown_rules(rules_root / "work-bundle"):
            failures = rules_module.validate_rule_file(rules_root, path)
            assert failures == [], failures
        index_failures = rules_module.validate_index(rules_root)
        work_bundle_index_failures = [
            failure for failure in index_failures if failure.startswith("index.yaml:") and "wb-" in failure
        ]
        assert work_bundle_index_failures == [], work_bundle_index_failures
    finally:
        if sys.path and sys.path[0] == str(REPO_ROOT / "scripts" / "work-bundle"):
            sys.path.pop(0)


def test_verification_evidence_before_claim_rule_is_always_loaded_and_indexed() -> None:
    rule = (REPO_ROOT / "rules/verification-evidence-before-claim.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "rules/index.yaml").read_text(encoding="utf-8")
    body = rule.split("---", 2)[2]

    assert "id: verification-evidence-before-claim" in rule
    assert "path: verification-evidence-before-claim.md" in index
    assert "load: always" in rule
    assert "exact claim" in rule
    assert "capable evidence" in rule
    assert "fresh, claim-relevant evidence" in rule
    assert "only the status that evidence supports" in rule
    assert "Knowledge Base Update" in rule
    assert "stale evidence" in rule
    assert "partial evidence" in rule
    assert "durable knowledge remains unresolved" in rule
    assert 150 <= len(body.split()) <= 250


def test_codegraph_rule_stays_index_gated_and_preserves_fallback() -> None:
    rule = (REPO_ROOT / "rules/agent-codegraph-first.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "rules/index.yaml").read_text(encoding="utf-8")

    gated_condition = "the targeted repository root contains `.codegraph/`"
    assert gated_condition in rule
    assert gated_condition in index
    assert "run `codegraph sync <repo-root>` after applicable repository preflight" in rule
    assert "before graph-derived source inspection, delegation context preparation, or editing" in rule
    assert "record `sync-failed`" in rule
    assert "post-change `codegraph sync <repo-root>`" in rule
    assert "Do not run `codegraph sync`, require CodeGraph use, or initialize CodeGraph" in rule
    assert "record no-index fallback instead" in rule
    assert "repository root lacked `.codegraph/`" in rule
    assert "record the concrete fallback reason before continuing" in rule


def test_project_context_preflight_rule_is_indexed_and_metadata_backed() -> None:
    rule = (REPO_ROOT / "rules/work-bundle/wb-project-context-preflight.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "rules/index.yaml").read_text(encoding="utf-8")

    assert "id: wb-project-context-preflight" in rule
    assert "id: wb-project-context-preflight" in index
    assert "path: work-bundle/wb-project-context-preflight.md" in index
    assert "$project_root/.work-bundle/project.yaml" in rule
    assert "$work_bundle_config_root/registry/projects.yaml" in rule
    assert "working_branch" in rule
    assert "last_commit_id" in rule
    assert "accepted executor-result handoffs" in rule
    assert "record `no-index` or `not-indexed` fallback" in rule
    assert "do not initialize CodeGraph or run `codegraph sync`" in rule


def test_validate_rules_rejects_scoped_rules_root(tmp_path: Path) -> None:
    root = tmp_path / "rules" / "work-bundle"
    root.mkdir(parents=True)
    (root / "wb-scoped-root.md").write_text(valid_rule_md("wb-scoped-root"), encoding="utf-8")

    result = run_wb("validate-rules", str(root))
    assert result.returncode == 1
    failures = json.loads(result.stdout)["failures"]
    assert any("scoped_rules_root_not_allowed" in failure for failure in failures)
    assert json.loads(result.stdout)["scope"] == "explicit"


def test_create_rules_rejects_scoped_rules_root(tmp_path: Path) -> None:
    root = tmp_path / "rules" / "work-bundle"
    root.mkdir(parents=True)
    (root / "wb-scoped-root.md").write_text(valid_rule_md("wb-scoped-root"), encoding="utf-8")

    result = run_wb("create-rules", str(root))
    assert result.returncode == 1
    failures = json.loads(result.stdout)["failures"]
    assert any("scoped_rules_root_not_allowed" in failure for failure in failures)
    assert not (root / "index.yaml").exists()


def test_scoped_validate_rules_resolves_toolkit_root(tmp_path: Path) -> None:
    toolkit = tmp_path / "toolkit"
    root = toolkit / "rules"
    scope = root / "work-bundle"
    scope.mkdir(parents=True)
    (scope / "wb-valid-rule.md").write_text(valid_rule_md("wb-valid-rule"), encoding="utf-8")
    created = run_wb("create-rules", str(root), env={"WB_WORK_BUNDLE_ROOT": str(toolkit)})
    assert created.returncode == 0, created.stdout + created.stderr

    result = run_wb(
        "validate-rules",
        "--scope",
        "toolkit",
        "--project-root",
        str(toolkit),
        env={"WB_WORK_BUNDLE_ROOT": str(toolkit)},
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["scope"] == "toolkit"
    assert Path(payload["rules_root"]) == root.resolve()


def test_scoped_validate_rules_resolves_global_and_project_roots(tmp_path: Path) -> None:
    config = tmp_path / "config"
    global_root = config / "rules"
    project = tmp_path / "project"
    project_root = project / ".work-bundle" / "rules"
    for root, rule_id in [(global_root, "global-cross-cutting"), (project_root, "project-cross-cutting")]:
        root.mkdir(parents=True)
        (root / f"{rule_id}.md").write_text(valid_rule_md(rule_id), encoding="utf-8")
        assert run_wb("create-rules", str(root), env={"WB_CONFIG_ROOT": str(config)}).returncode == 0

    global_result = run_wb("validate-rules", "--scope", "global", env={"WB_CONFIG_ROOT": str(config)})
    global_payload = json.loads(global_result.stdout)
    assert global_result.returncode == 0, global_result.stdout + global_result.stderr
    assert global_payload["scope"] == "global"
    assert Path(global_payload["rules_root"]) == global_root.resolve()

    project_result = run_wb(
        "validate-rules",
        "--scope",
        "project",
        "--project-root",
        str(project),
        env={"WB_CONFIG_ROOT": str(config)},
    )
    project_payload = json.loads(project_result.stdout)
    assert project_result.returncode == 0, project_result.stdout + project_result.stderr
    assert project_payload["scope"] == "project"
    assert Path(project_payload["rules_root"]) == project_root.resolve()


def test_toolkit_create_rules_blocks_when_project_root_differs_from_work_bundle_root(tmp_path: Path) -> None:
    toolkit = tmp_path / "toolkit"
    (toolkit / "rules").mkdir(parents=True)
    project = tmp_path / "project"
    project.mkdir()

    result = run_wb(
        "create-rules",
        "--scope",
        "toolkit",
        "--project-root",
        str(project),
        env={"WB_WORK_BUNDLE_ROOT": str(toolkit)},
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["status"] == "blocked"
    assert any("toolkit_scope_write_forbidden" in failure for failure in payload["failures"])


def test_effective_rule_registry_reports_optional_missing_and_duplicate_ids(tmp_path: Path) -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "work-bundle"))
    old_root = os.environ.get("WB_WORK_BUNDLE_ROOT")
    old_config = os.environ.get("WB_CONFIG_ROOT")
    try:
        os.environ["WB_WORK_BUNDLE_ROOT"] = str(tmp_path / "toolkit")
        os.environ["WB_CONFIG_ROOT"] = str(tmp_path / "config")
        sys.modules.pop("rules", None)
        import rules as rules_module

        toolkit_root = tmp_path / "toolkit" / "rules"
        project = tmp_path / "project"
        project_rules = project / ".work-bundle" / "rules"
        for root in [toolkit_root, project_rules]:
            (root / "work-bundle").mkdir(parents=True)
            (root / "work-bundle" / "wb-duplicate.md").write_text(valid_rule_md("wb-duplicate"), encoding="utf-8")
            rules_module.sync_index(root)

        registry = rules_module.build_effective_rule_registry(project)
        assert registry["status"] == "issues-found"
        assert "global" in registry["missing_optional"]
        assert any(str(failure).startswith("duplicate_rule_id:wb-duplicate:") for failure in registry["failures"])
    finally:
        if old_root is None:
            os.environ.pop("WB_WORK_BUNDLE_ROOT", None)
        else:
            os.environ["WB_WORK_BUNDLE_ROOT"] = old_root
        if old_config is None:
            os.environ.pop("WB_CONFIG_ROOT", None)
        else:
            os.environ["WB_CONFIG_ROOT"] = old_config
        if sys.path and sys.path[0] == str(REPO_ROOT / "scripts" / "work-bundle"):
            sys.path.pop(0)


def test_agents_template_load_always_is_unconditional_and_three_scopes_are_named() -> None:
    text = (REPO_ROOT / "references/assets/template/AGENTS.md").read_text(encoding="utf-8")
    assert "$work_bundle_root/rules/index.yaml" in text
    assert "$work_bundle_config_root/rules/index.yaml" in text
    assert "$project_root/.work-bundle/rules/index.yaml" in text
    assert "load `load: always` rule bodies immediately and unconditionally" in text
    assert "decompose it into rule-matching signals, then check discovered rule metadata" in text
    assert "decompose the current user request into task signals, then check all discovered rule metadata" in text
    assert "load `load: always` rules only when their scope is relevant" not in text
    assert "decompose the current user request before rule selection" not in text


def test_validate_rules_rejects_nested_scope_index(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    scope = root / "work-bundle"
    scope.mkdir(parents=True)
    (scope / "wb-valid-rule.md").write_text(valid_rule_md("wb-valid-rule"), encoding="utf-8")
    (scope / "index.yaml").write_text("rules: []\n", encoding="utf-8")

    result = run_wb("validate-rules", str(root))
    assert result.returncode == 1
    failures = json.loads(result.stdout)["failures"]
    assert "work-bundle/index.yaml:nested_index_not_allowed" in failures


def test_create_rules_migrates_legacy_yaml_to_markdown(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    root.mkdir()
    (root / "legacy.yaml").write_text(
        "\n".join(
            [
                "id: rule-legacy",
                "status: current",
                "scope: work-bundle",
                "enable_when: [legacy activation]",
                "severity: must",
                "required_behavior: [do required work]",
                "prohibited_behavior: [do not do prohibited work]",
                "validation: [inspect migrated rule]",
                "source_authority: [legacy source]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    created = run_wb("create-rules", str(root))
    assert created.returncode == 0, created.stdout + created.stderr
    assert not (root / "legacy.yaml").exists()
    assert (root / "legacy.md").exists()
    text = (root / "legacy.md").read_text(encoding="utf-8")
    assert "severity:" not in text
    assert "source_authority:" not in text

    validated = run_wb("validate-rules", str(root))
    assert validated.returncode == 0, validated.stdout + validated.stderr


def test_validate_rules_rejects_prohibited_front_matter(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    root.mkdir()
    (root / "bad.md").write_text(
        valid_rule_md("bad-rule", extra_front_matter="scope: work-bundle\n"),
        encoding="utf-8",
    )
    (root / "index.yaml").write_text(
        "rules:\n"
        "  - id: bad-rule\n"
        "    path: bad.md\n"
        "    applies_when:\n"
        "      - bad activation\n"
        "    enforcement: must\n"
        "    load: conditional\n"
        "    requires: []\n",
        encoding="utf-8",
    )

    result = run_wb("validate-rules", str(root))
    assert result.returncode == 1
    failures = json.loads(result.stdout)["failures"]
    assert "bad.md:prohibited_front_matter:scope" in failures


def test_validate_rules_rejects_empty_applies_when(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    root.mkdir()
    (root / "work-bundle").mkdir()
    (root / "work-bundle" / "wb-empty-when.md").write_text(
        valid_rule_md("wb-empty-when", applies_when=[]),
        encoding="utf-8",
    )
    run_wb("create-rules", str(root))

    result = run_wb("validate-rules", str(root))
    assert result.returncode == 1
    failures = json.loads(result.stdout)["failures"]
    assert "work-bundle/wb-empty-when.md:empty_applies_when" in failures


def test_validate_rules_rejects_forbidden_global_path(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    global_dir = root / "global"
    global_dir.mkdir(parents=True)
    (global_dir / "bad.md").write_text(valid_rule_md("cross-cutting-rule"), encoding="utf-8")
    run_wb("create-rules", str(root))

    result = run_wb("validate-rules", str(root))
    assert result.returncode == 1
    failures = json.loads(result.stdout)["failures"]
    assert "global/bad.md:forbidden_path:global" in failures


def test_validate_rules_rejects_scoped_rule_at_rules_root(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    root.mkdir()
    (root / "wb-at-root.md").write_text(valid_rule_md("wb-at-root"), encoding="utf-8")
    run_wb("create-rules", str(root))

    result = run_wb("validate-rules", str(root))
    assert result.returncode == 1
    failures = json.loads(result.stdout)["failures"]
    assert "wb-at-root.md:scoped_rule_at_root:wb-at-root:work-bundle" in failures


def test_validate_rules_accepts_valid_scoped_placement(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    scope = root / "work-bundle"
    scope.mkdir(parents=True)
    (scope / "wb-valid-rule.md").write_text(valid_rule_md("wb-valid-rule"), encoding="utf-8")
    run_wb("create-rules", str(root))

    result = run_wb("validate-rules", str(root))
    assert result.returncode == 0, result.stdout + result.stderr


def test_validate_rules_accepts_vague_applies_when_mechanically(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    scope = root / "work-bundle"
    scope.mkdir(parents=True)
    (scope / "wb-vague-when.md").write_text(
        valid_rule_md("wb-vague-when", applies_when=["when appropriate", "as needed"]),
        encoding="utf-8",
    )
    run_wb("create-rules", str(root))

    result = run_wb("validate-rules", str(root))
    assert result.returncode == 0, result.stdout + result.stderr
    failures = json.loads(result.stdout).get("failures", [])
    assert not any("vague" in failure for failure in failures)


def test_validate_rules_rejects_scope_id_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    scope = root / "keep-summarizing"
    scope.mkdir(parents=True)
    (scope / "wb-wrong-scope.md").write_text(valid_rule_md("wb-wrong-scope"), encoding="utf-8")
    run_wb("create-rules", str(root))

    result = run_wb("validate-rules", str(root))
    assert result.returncode == 1
    failures = json.loads(result.stdout)["failures"]
    assert "keep-summarizing/wb-wrong-scope.md:scope_id_mismatch:wb-wrong-scope:work-bundle" in failures


def test_index_paths_stable_across_double_sync(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    scope = root / "work-bundle"
    scope.mkdir(parents=True)
    (scope / "wb-index-stable.md").write_text(valid_rule_md("wb-index-stable"), encoding="utf-8")
    (root / "cross-cutting.md").write_text(valid_rule_md("cross-cutting-rule"), encoding="utf-8")

    first = run_wb("create-rules", str(root))
    assert first.returncode == 0, first.stdout + first.stderr
    index_after_first = (root / "index.yaml").read_text(encoding="utf-8")

    second = run_wb("create-rules", str(root))
    assert second.returncode == 0, second.stdout + second.stderr
    index_after_second = (root / "index.yaml").read_text(encoding="utf-8")

    assert index_after_first == index_after_second
    assert "path: work-bundle/wb-index-stable.md" in index_after_second
    assert "path: cross-cutting.md" in index_after_second
    assert "path: rules/" not in index_after_second
    assert "../" not in index_after_second


def test_index_entry_paths_relative_to_rules_root(tmp_path: Path) -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "work-bundle"))
    try:
        import rules as rules_module

        root = tmp_path / "rules"
        scope = root / "work-bundle"
        scope.mkdir(parents=True)
        rule_path = scope / "wb-relative-path.md"
        rule_path.write_text(valid_rule_md("wb-relative-path"), encoding="utf-8")

        entry = rules_module.index_entry(root, rule_path)
        assert entry["path"] == "work-bundle/wb-relative-path.md"

        first = rules_module.sync_index(root)
        second = rules_module.sync_index(root)
        assert first == second
        assert all(not str(entry["path"]).startswith("rules/") for entry in second)
        assert all(".." not in str(entry["path"]) for entry in second)
    finally:
        if sys.path and sys.path[0] == str(REPO_ROOT / "scripts" / "work-bundle"):
            sys.path.pop(0)


def test_violation_evaluation_rule_has_relaxed_trigger_and_routing_contract() -> None:
    rule = (REPO_ROOT / "rules/work-bundle/wb-violation-evaluation.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "rules/index.yaml").read_text(encoding="utf-8")

    relaxed_trigger = (
        "a conflict, violation, error, failed validation, contradictory workflow behavior, "
        "user interruption, or user correction occurs during WorkBundle-guided work"
    )
    assert relaxed_trigger in rule
    assert relaxed_trigger in index
    assert "work-bundle-scoped`, `project-scoped`, `mixed`, or `undetermined" in rule
    assert "Create or update minimal violation evidence for `work-bundle-scoped` and `mixed`" in rule
    assert "Report `project-scoped` findings as project blockers" in rule
    assert "Block for resolution when an `undetermined` finding affects authority" in rule


def test_violation_evaluation_stops_at_visible_workbundle_relatedness() -> None:
    rule = (REPO_ROOT / "rules/work-bundle/wb-violation-evaluation.md").read_text(encoding="utf-8")

    assert "Use visible evidence first" in rule
    assert "stop evaluation and proceed to the matching action" in rule
    assert "Stop tracing as soon as visible evidence establishes" in rule
    assert "Do not require full root-cause tracing after WorkBundle toolkit relatedness is visible" in rule
    assert "instruction -> plan -> plan skill -> source specification -> specification skill" in rule
    assert "mandatory chain-of-thought output" in rule


def test_violation_evidence_calls_evaluation_and_keeps_storage_boundary() -> None:
    evidence = (REPO_ROOT / "rules/work-bundle/wb-violation-evidence.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "rules/index.yaml").read_text(encoding="utf-8")

    trigger = "the Work Bundle rule is visible in AGENTS.md and any conflict, confliction, violation, contradiction, or user correction occurs"
    assert trigger in evidence
    assert trigger in index
    assert "requires: []" in evidence
    assert "requires: []" in index
    assert "immediately call `wb-violation-evaluation`" in evidence
    assert "Exit the violation evidence workflow without recording evidence" in evidence
    assert "classifies the first-observed finding as `work-bundle-scoped` or `mixed`" in evidence
    assert "Do not expand evidence capture into evaluation, root-cause investigation, or exhaustive workflow-chain tracing" in evidence
    assert "project-scoped findings from `wb-violation-evaluation` as blockers" in evidence
    assert "undetermined findings that affect authority, target scope, validation, or continuation as resolution blockers" in evidence


def test_violation_rules_support_same_scope_specification_owned_handling() -> None:
    evaluation = (REPO_ROOT / "rules/work-bundle/wb-violation-evaluation.md").read_text(encoding="utf-8")
    evidence = (REPO_ROOT / "rules/work-bundle/wb-violation-evidence.md").read_text(encoding="utf-8")

    assert "same-scope specification-owned" in evaluation
    assert "current project is the WorkBundle toolkit itself" in evaluation
    assert "exactly the current specification-owned work item" in evaluation
    assert "record the issue in the active specification source context, Open Questions, or review evidence" in evaluation
    assert "instead of creating a new violation evidence file" in evaluation
    assert "same_scope_specification_owned: true|false" in evaluation

    assert "same-scope specification-owned" in evidence
    assert "without recording a new evidence file" in evidence
    assert "active specification source context, Open Questions, or review evidence" in evidence
    assert "evidence persistence is not required" in evidence


def test_orchestration_rules_require_contract_barrier_and_review_settlement_evidence() -> None:
    handoff = (REPO_ROOT / "rules/orchestration/orch-handoff-required.md").read_text(encoding="utf-8")
    review = (REPO_ROOT / "rules/orchestration/orch-review-completion.md").read_text(encoding="utf-8")

    assert "contract_decoupling" in handoff
    assert "common contracts checked" in handoff
    assert "`peer_implementation_validation_used: false`" in handoff
    assert "barrier id, participant role, readiness `reached|blocked`" in handoff
    assert "every participant completed or blocked with executor-result handoffs before joint validation began" in handoff

    assert "accepted task-review status coherence" in review
    assert "Route missing handoff, status, validation, or review evidence to `review-blocked`" in review
    assert "Route incomplete durable knowledge work to `knowledge-blocked`" in review
    assert "Create or require plan repair only for a decomposition defect" in review
    assert "specification repair only for a requirement, design, or authority defect" in review
    assert "Do not create a repair specification for every failed review gate" in review


def test_execution_and_review_skills_carry_task003_flow_requirements() -> None:
    execute = (REPO_ROOT / "skills/orch-execute-plan/SKILL.md").read_text(encoding="utf-8")
    review = (REPO_ROOT / "skills/orch-review-plan/SKILL.md").read_text(encoding="utf-8")

    assert "Contract-decoupled participants validate against the common contract" in execute
    assert "accepted prior handoffs" in execute
    assert "reach the named barrier before convergence work" in execute
    assert "The scheduler does not perform code-quality review" in execute
    assert "acceptance_review.verdict: accept" in execute

    assert "Independent `dev-code-review` owns task-scoped implementation quality" in review
    assert "Do not broadly inspect source" in review
    assert "knowledge-blocked" in review
    assert "repair plan only" in review
    assert "repair specification" in review


def test_initialize_project_guidance_matches_create_rule_project_scope() -> None:
    initialize = (REPO_ROOT / "skills/wb-initialize-project/SKILL.md").read_text(encoding="utf-8")
    create_rule = (REPO_ROOT / "skills/wb-create-rule/SKILL.md").read_text(encoding="utf-8")

    assert "$project_root/.work-bundle/rules/" in create_rule
    assert ".work-bundle/rules/index.yaml" in initialize
    assert "root `rules/index.yaml` is legacy-only" in initialize
    assert "preserve it as a legacy artifact only" in initialize

    legacy_root_mentions = [
        line.strip()
        for line in initialize.splitlines()
        if "rules/index.yaml" in line and ".work-bundle/rules/index.yaml" not in line
    ]
    assert legacy_root_mentions
    assert all(("legacy" in line.lower() or "migration" in line.lower()) for line in legacy_root_mentions)
    assert "`.work-bundle/project.yaml`, `rules/index.yaml`" not in initialize


def test_initialize_project_v4_migration_guardrails_and_pressure_scenarios() -> None:
    initialize = (REPO_ROOT / "skills/wb-initialize-project/SKILL.md").read_text(encoding="utf-8")
    evals = json.loads((REPO_ROOT / "references/evals/work-bundle/evals.json").read_text(encoding="utf-8"))

    assert "migrate-control-plane" in initialize
    assert "--repository-remote" in initialize
    assert "load every applicable rule body in full" in initialize
    assert "do not edit the project registry directly" in initialize
    assert "do not change an external repository's Git config" in initialize
    prompts = "\n".join(item["prompt"] for item in evals["evals"])
    assert "live network remote and registry network remote conflict" in prompts
    assert "ordinary v3 single-repository workspace" in prompts
    assert "portable v4 single-repository workspace" in prompts
    assert "remote rejects the push" in prompts
    assert "In both workspace modes, create or preserve `$workspace_root/script/index.yaml`" in initialize
    assert "In both workspace modes, create or preserve `$workspace_root/credentials/credentials.yaml`" in initialize


def test_single_repository_workspace_resource_contracts_converge() -> None:
    metadata_contract = (REPO_ROOT / "references/wb-workspace-metadata-v3-contract.yaml").read_text(encoding="utf-8")
    credential_contract = (REPO_ROOT / "references/wb-credential-use-contract.yaml").read_text(encoding="utf-8")
    security_rule = (REPO_ROOT / "rules/security-exclusion.md").read_text(encoding="utf-8")
    script_rule = (REPO_ROOT / "rules/work-bundle/wb-script-instruction.md").read_text(encoding="utf-8")

    assert "workspace_modes: [single-repository, multi-repository]" in credential_contract
    assert "workspace_resources: forbidden" not in metadata_contract
    assert "forbidden_runtime_paths: [script, credentials]" not in metadata_contract
    assert "in both single- and multi-repository modes" in security_rule
    assert "Permit workspace utilities in both single- and multi-repository modes" in script_rule
    assert "multi-repository-only" not in "\n".join(
        (credential_contract, security_rule, script_rule)
    )


def test_workspace_ecosystem_documentation_and_external_registry_boundary() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    scripts_readme = (REPO_ROOT / "scripts/work-bundle/README.md").read_text(encoding="utf-8")
    registry_template = (REPO_ROOT / "references/assets/template/skill-registry.yaml").read_text(encoding="utf-8")
    registry_contract = (REPO_ROOT / "references/wb-register-skill-contract.yaml").read_text(encoding="utf-8")

    assert "`workspace_root`" in readme
    assert "`project_root`" in readme
    assert "singular `script/`" in readme
    assert "credentials/credentials.yaml" in readme
    assert "--scope project --workspace-root <workspace-root>" in scripts_readme
    assert "bootstrap.yaml` field `skill_registry`" in scripts_readme
    assert "runtime skill registry" in scripts_readme and "external-only" in scripts_readme
    assert "wb-credential-use` and `wb-migrate-to-multi-repository" in scripts_readme
    assert "scope: external-skills-only" in registry_template
    assert "built_in_work_bundle_skills: toolkit-owned-not-registered" in registry_template
    assert "type: internal" not in registry_template
    assert "unconfirmed_merge_forbidden: true" in registry_template
    assert "registry_path_source: bootstrap.skill_registry" in registry_contract
    assert "scope: external-skills-only" in registry_contract
    assert "non_external_entries_must_be_rejected: true" in registry_contract
    assert "explicit_confirmation_required_for_merge: true" in registry_contract


def test_credential_contract_skill_and_rules_use_closed_form_specific_adapters() -> None:
    contract = (REPO_ROOT / "references/wb-credential-use-contract.yaml").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "skills/wb-credential-use/SKILL.md").read_text(encoding="utf-8")
    credential_rule = (REPO_ROOT / "rules/work-bundle/wb-credential-use.md").read_text(encoding="utf-8")
    security_rule = (REPO_ROOT / "rules/security-exclusion.md").read_text(encoding="utf-8")

    assert "closed_forms: true" in contract and "ids_unique: true" in contract
    for form in (
        "password_file", "username_password", "ssh_private_key", "passphrase",
        "environment_reference", "external_secret_reference",
    ):
        assert f"{form}:" in contract
    skill_mechanisms = {
        "path-reference": "path reference",
        "protected-fd": "protected file descriptor",
        "stdin": "stdin",
        "child-environment": "child-scoped environment",
        "keychain": "keychain",
        "ssh-agent": "agent",
    }
    for mechanism, phrase in skill_mechanisms.items():
        assert mechanism in contract and phrase in skill.lower()
    assert "Suppress raw child stdout/stderr" in skill
    assert "adapter-result contract" in security_rule
    assert "form-specific adapter" in credential_rule


def test_work_bundle_skill_registry_rule_excludes_builtin_skills() -> None:
    rule = (REPO_ROOT / "rules/work-bundle/wb-skill-registry.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "skills/wb-register-skill/SKILL.md").read_text(encoding="utf-8")
    rule_index = (REPO_ROOT / "rules/index.yaml").read_text(encoding="utf-8")

    assert "external skill registry" in rule
    assert "built-in WorkBundle skills" in rule
    assert "Reject any attempt to register a built-in WorkBundle skill" in rule
    assert "task.registers_external_skill" in rule_index
    assert "task.registers_skill" not in rule_index
    assert "only for external skills" in skill
    assert "~/.work-bundle/registry/skill-registry.yaml" in skill


def test_registry_entry_validation_rejects_builtin_and_internal_skills(tmp_path: Path) -> None:
    common = (
        "mode: native\npriority: optional\nused_by: [backend-developer]\n"
        "stages: [implementation]\nallowed_outputs: [result]\n"
        "validation: [bounded]\nfallback: manual\n"
    )
    internal = tmp_path / "internal.yaml"
    internal.write_text(f"type: internal\nsource: /tmp/external-skill/SKILL.md\n{common}", encoding="utf-8")
    builtin = tmp_path / "builtin.yaml"
    builtin.write_text(
        f"type: external\nsource: {REPO_ROOT / 'skills/wb-credential-use/SKILL.md'}\n{common}",
        encoding="utf-8",
    )

    internal_result = run_wb("validate-registry-entry", str(internal))
    builtin_result = run_wb("validate-registry-entry", str(builtin))

    assert internal_result.returncode == 1
    assert "external-type-required" in internal_result.stdout
    assert builtin_result.returncode == 1
    assert "built-in-work-bundle-skill-forbidden" in builtin_result.stdout


def test_register_skill_refuses_builtin_before_registry_mutation(tmp_path: Path) -> None:
    registry = tmp_path / "registry.yaml"
    registry.write_text("skills: {}\n", encoding="utf-8")
    entry = tmp_path / "builtin.yaml"
    entry.write_text(
        "type: external\n"
        f"source: {REPO_ROOT / 'skills/wb-migrate-to-multi-repository/SKILL.md'}\n"
        "mode: native\npriority: optional\nused_by: [devops-engineer]\n"
        "stages: [implementation]\nallowed_outputs: [migration-result]\n"
        "validation: [bounded]\nfallback: manual\n",
        encoding="utf-8",
    )

    result = run_wb("register-skill", "--registry", str(registry), "--entry", str(entry), "--confirmed")

    assert result.returncode == 2
    assert "built-in-work-bundle-skill-forbidden" in result.stdout
    assert registry.read_text(encoding="utf-8") == "skills: {}\n"
