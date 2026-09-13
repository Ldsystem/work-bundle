from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
if str(ORCHESTRATION) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATION))

import bounded_closure  # noqa: E402
import completion_provenance  # noqa: E402
import plans  # noqa: E402


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _workspace(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "workspace"
    metadata = root / ".work-bundle/project.yaml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        yaml.safe_dump(
            {
                "metadata_version": 4,
                "workspace": {"id": "workspace-test", "mode": "single-repository"},
                "orchestration_control": {
                    "schema_version": 1,
                    "post_execution_review_round_limit": 5,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    active_spec = root / ".work-bundle/orchestration/spec/active"
    active_plan = root / ".work-bundle/orchestration/plan/active"
    active_spec.mkdir(parents=True)
    (active_plan / "plan-flow").mkdir(parents=True)
    (active_spec / "spec-origin.md").write_text(
        "---\nid: spec-origin\nstatus: verified\n---\n# Original\n", encoding="utf-8"
    )
    (active_plan / "plan-origin.md").write_text(
        "---\nid: plan-flow\nstatus: In progress\n---\n# Plan\n", encoding="utf-8"
    )
    (active_plan / "plan-flow/task-001.md").write_text(
        "---\nid: task-001\nplan_id: plan-flow\nphase_id: phase-001\nstatus: Completed\n---\n# Task\n",
        encoding="utf-8",
    )
    residual = active_spec / "spec-residual.md"
    residual.write_text(
        "---\nid: spec-residual\nstatus: active\n---\n"
        "# Residual findings\n\n- REQ-005 remains unaccepted because receipt-1 is missing.\n",
        encoding="utf-8",
    )
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "-C", str(source), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "Test"], check=True)
    (source / "product.txt").write_text("unresolved\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "baseline"], check=True)
    return root, {
        "repository_id": "product-main",
        "project_root": str(source),
        "commit": _git(source, "rev-parse", "HEAD"),
        "tree": _git(source, "rev-parse", "HEAD^{tree}"),
    }


def _exhaust(root: Path) -> None:
    for number in range(1, 6):
        round_record = bounded_closure.begin_review_round(
            root,
            flow_id="plan-flow",
            request_id=f"request-{number}",
            review_id=f"review-{number}",
            target_identity={
                "artifact_id": "plan-flow",
                "revision": str(number),
                "sha256": hashlib.sha256(str(number).encode()).hexdigest(),
                "source_tree": "a" * 40,
            },
            executor_attempts=[{"execution_id": "executor-1", "state": "completed"}],
            known_missing_evidence=["accepted_result"],
        )
        bounded_closure.complete_review_round(
            root,
            flow_id="plan-flow",
            round_id=str(round_record["round_id"]),
            outcome="blocked",
            audit_block={"code": "missing-evidence", "missing": ["accepted_result"]},
        )


def _finalize(root: Path, baseline: dict[str, str], **overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "flow_id": "plan-flow",
        "request_id": "finalize-1",
        "blocker_id": "BLOCK-plan-flow",
        "residual_spec_id": "spec-residual",
        "residual_spec": root / ".work-bundle/orchestration/spec/active/spec-residual.md",
        "origin_spec_id": "spec-origin",
        "origin_plan_id": "plan-flow",
        "source_baselines": [baseline],
        "knowledge_return": {"status": "not-needed", "evidence_ref": None},
        "operator_authorized": False,
    }
    arguments.update(overrides)
    return bounded_closure.finalize_with_blockers(root, **arguments)


def test_fifth_round_finalization_persists_blocker_then_archives_origins_and_is_retry_safe(
    tmp_path: Path,
) -> None:
    root, baseline = _workspace(tmp_path)
    _exhaust(root)

    first = _finalize(root, baseline)
    second = _finalize(root, baseline)

    assert second == first
    assert first["outcome"] == "closed_with_blockers"
    control = yaml.safe_load((root / ".work-bundle/project.yaml").read_text(encoding="utf-8"))[
        "orchestration_control"
    ]
    assert control["blockers"] == [
        {
            "id": "BLOCK-plan-flow",
            "status": "active",
            "origin_plan": "plan-flow",
            "origin_spec": "spec-origin",
            "specification": ".work-bundle/orchestration/spec/active/spec-residual.md",
            "source_baselines": [
                {
                    "repository_id": "product-main",
                    "commit": baseline["commit"],
                    "tree": baseline["tree"],
                }
            ],
        }
    ]
    assert control["closed_flows"][0]["outcome"] == "closed_with_blockers"
    assert not (root / ".work-bundle/orchestration/spec/active/spec-origin.md").exists()
    assert (root / ".work-bundle/orchestration/spec/archived/spec-origin.md").is_file()
    assert not (root / ".work-bundle/orchestration/plan/active/plan-origin.md").exists()
    assert (root / ".work-bundle/orchestration/plan/archived/plan-origin.md").is_file()
    assert (root / ".work-bundle/orchestration/plan/archived/plan-flow/task-001.md").is_file()


def test_forced_finalization_requires_exhaustion_or_explicit_operator_authority(
    tmp_path: Path,
) -> None:
    root, baseline = _workspace(tmp_path)

    with pytest.raises(
        bounded_closure.BoundedClosureError,
        match="WB_POST_EXECUTION_FINALIZATION_NOT_AUTHORIZED",
    ):
        _finalize(root, baseline)

    result = _finalize(root, baseline, operator_authorized=True)
    assert result["outcome"] == "closed_with_blockers"


def test_invalid_or_dirty_source_baseline_stops_before_blocker_and_archive(tmp_path: Path) -> None:
    root, baseline = _workspace(tmp_path)
    _exhaust(root)
    Path(baseline["project_root"]).joinpath("product.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(
        bounded_closure.BoundedClosureError,
        match="WB_POST_EXECUTION_SOURCE_BASELINE_DIRTY",
    ):
        _finalize(root, baseline)

    control = yaml.safe_load((root / ".work-bundle/project.yaml").read_text(encoding="utf-8"))[
        "orchestration_control"
    ]
    assert control.get("blockers", []) == []
    assert (root / ".work-bundle/orchestration/spec/active/spec-origin.md").is_file()
    ledger = json.loads(
        (root / ".work-bundle/runtime/orchestration-control/post-execution-review-rounds-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["flows"]["plan-flow"]["finalization"]["state"] == "required"


@pytest.mark.parametrize("entrypoint", ["orch.py", "wb.py"])
def test_both_public_cli_families_run_the_shared_forced_finalizer(
    tmp_path: Path, entrypoint: str,
) -> None:
    root, baseline = _workspace(tmp_path)
    _exhaust(root)
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / entrypoint),
            "finalize-with-blockers",
            "--project-root",
            str(root),
            "--flow-id",
            "plan-flow",
            "--request-id",
            "finalize-cli",
            "--blocker-id",
            "BLOCK-plan-flow",
            "--residual-spec-id",
            "spec-residual",
            "--residual-spec",
            str(root / ".work-bundle/orchestration/spec/active/spec-residual.md"),
            "--origin-spec-id",
            "spec-origin",
            "--origin-plan-id",
            "plan-flow",
            "--source-baselines",
            json.dumps([baseline]),
            "--knowledge-return",
            json.dumps({"status": "not-needed", "evidence_ref": None}),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["outcome"] == "closed_with_blockers"


def test_interruption_after_archive_is_recorded_and_retry_finishes_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, baseline = _workspace(tmp_path)
    _exhaust(root)
    original_release = plans.release_plan_bindings_for_forced_finalization

    with monkeypatch.context() as scoped:
        scoped.setattr(
            plans,
            "release_plan_bindings_for_forced_finalization",
            lambda *_args: (_ for _ in ()).throw(OSError("injected release interruption")),
        )
        with pytest.raises(
            bounded_closure.BoundedClosureError,
            match="WB_POST_EXECUTION_FINALIZATION_INCOMPLETE",
        ):
            _finalize(root, baseline)

    ledger = json.loads(
        (root / ".work-bundle/runtime/orchestration-control/post-execution-review-rounds-v1.json").read_text(
            encoding="utf-8"
        )
    )
    finalization = ledger["flows"]["plan-flow"]["finalization"]
    assert finalization["state"] == "administrative_incomplete"
    assert finalization["incomplete"]["stage"] == "ownership_release"
    assert (root / ".work-bundle/orchestration/plan/archived/plan-origin.md").is_file()

    monkeypatch.setattr(plans, "release_plan_bindings_for_forced_finalization", original_release)
    assert _finalize(root, baseline)["outcome"] == "closed_with_blockers"


def test_retry_finishes_plan_directory_move_after_root_file_was_already_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, baseline = _workspace(tmp_path)
    _exhaust(root)
    original_move = plans.move_to_archive
    plan_move_count = 0

    def interrupt_second_plan_move(path: Path, active: Path, archived: Path) -> Path:
        nonlocal plan_move_count
        plan_move_count += 1
        if plan_move_count == 2:
            raise OSError("injected directory move interruption")
        return original_move(path, active, archived)

    with monkeypatch.context() as scoped:
        scoped.setattr(plans, "move_to_archive", interrupt_second_plan_move)
        with pytest.raises(
            bounded_closure.BoundedClosureError,
            match="WB_POST_EXECUTION_FINALIZATION_INCOMPLETE",
        ):
            _finalize(root, baseline)

    assert (root / ".work-bundle/orchestration/plan/archived/plan-origin.md").is_file()
    assert (root / ".work-bundle/orchestration/plan/active/plan-flow/task-001.md").is_file()
    assert _finalize(root, baseline)["outcome"] == "closed_with_blockers"
    assert (root / ".work-bundle/orchestration/plan/archived/plan-flow/task-001.md").is_file()


def test_forced_finalization_releases_active_plan_binding(tmp_path: Path) -> None:
    root, baseline = _workspace(tmp_path)
    _exhaust(root)
    store = completion_provenance.ManagedProvenanceStore(
        root / ".work-bundle/runtime/completion-provenance"
    )
    ownership = completion_provenance.FailureOwnershipV1.create(
        store,
        "binding-plan-flow-task-001",
        "local_project",
        "task-001",
    ).to_dict()
    binding_path = root / ".work-bundle/runtime/execution/plan-flow/task-001/execution-binding.json"
    binding_path.parent.mkdir(parents=True)
    binding_path.write_text(
        json.dumps({"plan_id": "plan-flow", "task_id": "task-001", "ownership": ownership}),
        encoding="utf-8",
    )

    _finalize(root, baseline)

    updated = json.loads(binding_path.read_text(encoding="utf-8"))
    assert updated["ownership"]["state"] == "released"


def test_finalization_never_launches_validation_or_review_subprocesses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, baseline = _workspace(tmp_path)
    _exhaust(root)
    real_run = bounded_closure.subprocess.run
    observed: list[list[str]] = []

    def guarded(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.append(argv)
        assert argv[0] == "git"
        assert not any(token in {"pytest", "reviewer", "validate-executor-result"} for token in argv)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(bounded_closure.subprocess, "run", guarded)
    _finalize(root, baseline)

    assert observed


def test_supplied_residual_spec_is_materialized_as_active_blocker_evidence(tmp_path: Path) -> None:
    root, baseline = _workspace(tmp_path)
    _exhaust(root)
    active = root / ".work-bundle/orchestration/spec/active/spec-residual.md"
    content = active.read_bytes()
    active.unlink()
    supplied = tmp_path / "supplied-residual.md"
    supplied.write_bytes(content)

    result = _finalize(root, baseline, residual_spec=supplied)

    assert result["residual_spec"]["path"].endswith("spec/active/supplied-residual.md")
    assert (root / result["residual_spec"]["path"]).read_bytes() == content


def test_invalid_knowledge_return_leaves_blocker_before_archive_and_can_be_retried(
    tmp_path: Path,
) -> None:
    root, baseline = _workspace(tmp_path)
    _exhaust(root)

    with pytest.raises(
        bounded_closure.BoundedClosureError,
        match="WB_POST_EXECUTION_KNOWLEDGE_RETURN_INVALID",
    ):
        _finalize(
            root,
            baseline,
            knowledge_return={"status": "blocked", "evidence_ref": None},
        )

    control = yaml.safe_load((root / ".work-bundle/project.yaml").read_text(encoding="utf-8"))[
        "orchestration_control"
    ]
    assert control["blockers"][0]["id"] == "BLOCK-plan-flow"
    assert (root / ".work-bundle/orchestration/plan/active/plan-origin.md").is_file()
    assert _finalize(root, baseline)["outcome"] == "closed_with_blockers"


def test_begin_review_round_public_admission_uses_explicit_flow_id(tmp_path: Path) -> None:
    root, _baseline = _workspace(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/orch.py"),
            "begin-review-round",
            "--project-root",
            str(root),
            "--flow-id",
            "plan-flow",
            "--request-id",
            "request-admission",
            "--review-id",
            "review-admission",
            "--target-identity",
            json.dumps(
                {
                    "artifact_id": "plan-flow",
                    "revision": "1",
                    "sha256": "b" * 64,
                    "source_tree": "c" * 40,
                }
            ),
            "--executor-attempts",
            json.dumps([{"execution_id": "executor-1", "state": "completed"}]),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["flow_id"] == "plan-flow"
