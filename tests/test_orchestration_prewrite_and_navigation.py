from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
loaded_core = sys.modules.get("core")
loaded_core_path = Path(getattr(loaded_core, "__file__", "")) if loaded_core is not None else None
if loaded_core_path is not None and ORCHESTRATION not in loaded_core_path.parents:
    sys.modules.pop("core", None)
sys.path.insert(0, str(ORCHESTRATION))

import core  # noqa: E402
import documents  # noqa: E402
import doctor  # noqa: E402
import evaluation_identity  # noqa: E402
import handoffs  # noqa: E402
import plans  # noqa: E402
import specs  # noqa: E402


def _args(workspace: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "workspace_root": str(workspace),
        "project_root": None,
        "id": "plan-prewrite",
        "title": "Pre-write boundary",
        "purpose": "Reject invalid content without workspace mutation",
        "component": "orchestration",
        "version": "1.0",
        "content_file": "",
        "status": "draft",
        "filename": None,
        "source_spec_id": "spec-prewrite",
        "plan_id": None,
        "task_id": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _bind_clean_workspace(
    monkeypatch: pytest.MonkeyPatch, workspace: Path, *modules: object
) -> None:
    for module in modules:
        monkeypatch.setattr(module, "resolve_workspace_root", lambda _args: workspace)
        if hasattr(module, "resolve_working_workspace"):
            monkeypatch.setattr(module, "resolve_working_workspace", lambda _root: None)
        if hasattr(module, "orchestration_root"):
            monkeypatch.setattr(
                module,
                "orchestration_root",
                lambda _args: workspace / ".work-bundle/orchestration",
            )
        if hasattr(module, "rel"):
            monkeypatch.setattr(
                module,
                "rel",
                lambda path, _args: Path(path).resolve().relative_to(workspace).as_posix(),
            )


def test_invalid_specification_and_plan_inputs_do_not_mutate_clean_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _bind_clean_workspace(monkeypatch, workspace, core, specs, plans)

    invalid_spec = tmp_path / "invalid-spec.md"
    invalid_spec.write_text("---\nid: caller-owned\n---\nBody\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="structural field override"):
        specs.cmd_write_spec(
            _args(workspace, id="spec-prewrite", content_file=str(invalid_spec))
        )
    assert not (workspace / ".work-bundle").exists()

    invalid_plan = tmp_path / "invalid-plan.yaml"
    invalid_plan.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        plans,
        "read_artifact",
        lambda *_args, **_kwargs: {"data": {"status": "verified"}},
    )
    with pytest.raises(SystemExit, match="schema validation failed"):
        plans.cmd_write_plan(_args(workspace, content_file=str(invalid_plan)))
    assert not (workspace / ".work-bundle").exists()


def test_current_initialization_creates_no_retired_handoff_or_aggregate_index_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        core,
        "orchestration_root",
        lambda _args: workspace / ".work-bundle/orchestration",
    )

    core.init_dirs(_args(workspace))

    root = workspace / ".work-bundle/orchestration"
    for retired in (
        "handoff/orchestration",
        "handoff/executor",
        "handoff/index.jsonl",
        "plan/index.jsonl",
    ):
        assert not (root / retired).exists()
    for current in (
        "spec/active",
        "plan/active",
        "result/executor/active",
        "result/accepted/active",
        "review/implementation/active",
        "review/final/active",
    ):
        assert (root / current).is_dir()


def test_current_specification_and_plan_writes_create_only_canonical_stores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _bind_clean_workspace(monkeypatch, workspace, core, specs, plans)
    spec_input = tmp_path / "spec.md"
    spec_input.write_text(
        "---\nproject: demo\nsource_knowledge: []\nrelated_handoffs: []\n"
        "tags: [current]\nexecution_workspace: "
        "{isolation: existing, profile: default, cleanup: manual}\n---\n"
        "# Current specification\n",
        encoding="utf-8",
    )
    specs.cmd_write_spec(
        _args(
            workspace,
            id="spec-prewrite",
            content_file=str(spec_input),
            status="verified",
        )
    )
    plan_input = tmp_path / "plan.yaml"
    plan_input.write_text(
        yaml.safe_dump(
            {
                "source_coverage": [
                    {
                        "source_id": "REQ-001",
                        "obligation_kind": "requirement",
                        "phase_ids": ["phase-prewrite"],
                    }
                ],
                "authority": {"decision": "source specification"},
                "strategy": {"summary": "one phase"},
                "phase_index": [{"id": "phase-prewrite", "order": 1}],
                "dependency_graph": {},
                "risks": [],
                "validation_strategy": [{"id": "VAL-001", "kind": "process"}],
                "completion_criteria": ["The current plan is stored."],
                "knowledge_base_update": {"action": "none"},
                "semantic_loop": {"result": "converged"},
                "execution_workspace": {
                    "isolation": "existing",
                    "profile": "default",
                    "cleanup": "manual",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    plans.cmd_write_plan(_args(workspace, content_file=str(plan_input)))

    root = workspace / ".work-bundle/orchestration"
    assert (root / "spec/active/spec-prewrite.spec.md").is_file()
    assert (root / "plan/active/plan-prewrite.plan.yaml").is_file()
    for retired in (
        "handoff/orchestration",
        "handoff/executor",
        "handoff/index.jsonl",
        "plan/index.jsonl",
    ):
        assert not (root / retired).exists()


def test_initialization_manifest_provisions_current_stores_only() -> None:
    manifest = yaml.safe_load(
        (REPO_ROOT / "references/wb-initialize-project-default-work-bundle-tree.yaml").read_text(
            encoding="utf-8"
        )
    )
    roots = set(manifest["roots"])
    for retired in (
        ".work-bundle/orchestration/handoff/orchestration/active",
        ".work-bundle/orchestration/handoff/executor/active",
        ".work-bundle/orchestration/reviews",
    ):
        assert retired not in roots
    for current in (
        ".work-bundle/orchestration/result/executor/active",
        ".work-bundle/orchestration/result/accepted/active",
        ".work-bundle/orchestration/review/implementation/active",
        ".work-bundle/orchestration/review/final/active",
    ):
        assert current in roots


def test_doctor_uses_the_same_current_catalog_as_runtime_writers() -> None:
    assert doctor.CATALOG.resolve() == plans.CATALOG_PATH.resolve()
    assert doctor.CATALOG.name == "artifact-family-catalog-v5.yaml"


def test_legacy_knowledge_migration_and_handoff_constants_are_not_public() -> None:
    help_result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/ks.py"), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "migrate-v3" in help_result.stdout
    assert "migrate-legacy" not in help_result.stdout
    assert not hasattr(core, "HANDOFF_STATUSES")
    assert not hasattr(core, "HANDOFF_TYPES")


def test_evaluation_observation_exclusions_use_current_result_and_review_stores() -> None:
    roots = set(evaluation_identity.OBSERVATION_ARTIFACT_ROOTS)
    assert ".work-bundle/orchestration/result/" in roots
    assert ".work-bundle/orchestration/review/" in roots
    assert ".work-bundle/orchestration/handoff/" not in roots
    assert ".work-bundle/orchestration/reviews/" not in roots


def test_current_rules_and_knowledge_reference_have_no_legacy_handoff_store() -> None:
    artifact_rule = (
        REPO_ROOT / "rules/orchestration/orch-artifact-authoring.md"
    ).read_text(encoding="utf-8")
    knowledge_rule = (
        REPO_ROOT / "rules/keep-summarizing/ks-knowledge-boundary.md"
    ).read_text(encoding="utf-8")
    workflow = (
        REPO_ROOT / "references/assets/keep-summarizing/workflow.md"
    ).read_text(encoding="utf-8")
    assert "handoff-orchestration-v1.md" not in artifact_rule
    assert "Orchestration handoff" not in artifact_rule
    for text in (knowledge_rule, workflow):
        assert ".work-bundle/orchestration/handoff/" not in text
        assert ".work-bundle/orchestration/result/" in text
        assert ".work-bundle/orchestration/review/" in text


def test_wor126_orchestration_rules_satisfy_contract_and_index_metadata() -> None:
    rule_ids = (
        "orch-bounded-closure",
        "orch-handoff-required",
        "orch-orchestration-boundary",
        "orch-review-completion",
    )
    index = yaml.safe_load((REPO_ROOT / "rules/index.yaml").read_text(encoding="utf-8"))
    entries = {entry["id"]: entry for entry in index["rules"]}
    for rule_id in rule_ids:
        path = REPO_ROOT / "rules/orchestration" / f"{rule_id}.md"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        end = text.index("\n---\n", 4)
        front_matter = yaml.safe_load(text[4:end])
        for section in ("Purpose", "Must", "Must Not", "Validation", "On Violation"):
            assert f"## {section}" in text
        assert entries[rule_id] == {
            "id": rule_id,
            "path": f"orchestration/{rule_id}.md",
            "applies_when": front_matter["applies_when"],
            "enforcement": front_matter["enforcement"],
            "load": front_matter["load"],
            "requires": front_matter["requires"],
        }


def test_retired_workflow_branch_reader_and_handoff_contract_are_excluded() -> None:
    help_result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "workflow-branches" not in help_result.stdout
    doctor_source = (REPO_ROOT / "scripts/work-bundle/doctor.py").read_text(encoding="utf-8")
    dispatcher_source = (REPO_ROOT / "scripts/work-bundle/dispatcher.py").read_text(encoding="utf-8")
    assert "orchestration/reviews" not in doctor_source
    assert "workflow-branches" not in dispatcher_source
    contract = (
        REPO_ROOT
        / "references/assets/orchestration/contract/handoff-orchestration-v1.md"
    ).read_text(encoding="utf-8")
    assert "historical exclusion" in contract.lower()
    assert "no compatibility authority" in contract.lower()
    assert "readable and indexable" not in contract.lower()


def test_current_orchestration_guidance_names_executor_results_and_direct_reviews() -> None:
    readme = (REPO_ROOT / "scripts/orchestration/README.md").read_text(encoding="utf-8")
    for current in (
        "write-executor-result",
        "write-implementation-review",
        "write-final-workflow-review",
        ".work-bundle/orchestration/result/executor/",
        ".work-bundle/orchestration/review/implementation/",
    ):
        assert current in readme
    for retired in (
        "observe-task-validation",
        "validate-executor-result",
        "runtime/handoff/review",
        "before writing the handoff",
    ):
        assert retired not in readme

    rule_path = REPO_ROOT / "rules/orchestration/orch-knowledge-gateway.md"
    rule_text = rule_path.read_text(encoding="utf-8")
    assert "canonical `executor-result-v1`" in rule_text
    assert "orchestration handoff" not in rule_text
    assert "executor-result handoff" not in rule_text
    assert "execution-completion handoffs" not in rule_text

    index = yaml.safe_load((REPO_ROOT / "rules/index.yaml").read_text(encoding="utf-8"))
    entry = next(item for item in index["rules"] if item["id"] == "orch-knowledge-gateway")
    front_matter = yaml.safe_load(rule_text[4 : rule_text.index("\n---\n", 4)])
    assert entry["applies_when"] == front_matter["applies_when"]


def _patch_navigation_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "init_dirs", lambda _args: None)
    monkeypatch.setattr(
        documents,
        "index_specs",
        lambda _args: [{"artifact_type": "specification", "id": "spec-current", "status": "verified"}],
    )
    monkeypatch.setattr(
        documents,
        "index_plans",
        lambda _args: [{"artifact_type": "task", "id": "task-current", "status": "planned"}],
    )
    results = lambda _args: [
        {
            "artifact_type": "executor-result",
            "id": "result-current",
            "plan_id": "plan-current",
            "task_id": "task-current",
            "result_state": "active",
        }
    ]
    if hasattr(documents, "list_executor_results"):
        monkeypatch.setattr(documents, "list_executor_results", results)
    else:
        monkeypatch.setattr(documents, "index_handoffs", results)


def test_public_navigation_uses_current_executor_result_names_and_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_navigation_sources(monkeypatch)
    monkeypatch.setattr(
        documents,
        "orchestration_root",
        lambda _args: tmp_path / ".work-bundle/orchestration",
    )

    documents.cmd_state(_args(tmp_path))
    state = json.loads(capsys.readouterr().out)
    assert state["executor_results"] == {"active": 1}
    assert "handoffs" not in state

    documents.cmd_next_action_candidates(_args(tmp_path))
    action = json.loads(capsys.readouterr().out)
    assert action == {
        "action": "review-executor-result",
        "executor_result_id": "result-current",
        "reason": "active executor result exists",
    }


def test_related_navigation_never_reads_legacy_aggregate_indexes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_navigation_sources(monkeypatch)
    monkeypatch.setattr(
        documents,
        "orchestration_root",
        lambda _args: tmp_path / ".work-bundle/orchestration",
    )
    monkeypatch.setattr(
        documents,
        "load_index",
        lambda _path: (_ for _ in ()).throw(AssertionError("legacy aggregate index read")),
        raising=False,
    )

    documents.cmd_related(_args(tmp_path, id="result-current"))

    assert json.loads(capsys.readouterr().out)["id"] == "result-current"
    assert not hasattr(handoffs, "index_handoffs")
