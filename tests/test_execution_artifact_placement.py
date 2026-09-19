from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import execution_context  # noqa: E402
from core import resolve_execution_artifact_path  # noqa: E402


@pytest.mark.parametrize(
    "path",
    [
        "evals/wor112/result.json",
        "evals/issue-112/manifest.json",
        "tests/test_wor112_acceptance.py",
        "tests/test_issue_112_evidence.py",
        "orchestration/executions/plan-001/result.json",
    ],
)
def test_static_admission_rejects_issue_run_artifacts_in_source(path: str) -> None:
    task = {"files": {"write": [path]}}
    with pytest.raises(SystemExit, match="source-local execution artifact"):
        execution_context._assert_no_source_local_execution_artifacts(task, Path("task.md"))


def test_static_admission_allows_only_proven_historical_cleanup_targets(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    historical = source / "tests/test_wor108_context_projection.py"
    historical.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    historical.write_text("def test_historical(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "historical execution test"], cwd=source, check=True)
    accepted_baseline = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source, check=True, capture_output=True, text=True
    ).stdout.strip()
    historical.unlink()
    subprocess.run(["git", "add", "-u"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "remove historical execution test"], cwd=source, check=True)
    task = {
        "target_files": ["tests/test_wor108_context_projection.py"],
        "truth_basis": {"purpose": "Remove execution-only source residue."},
        "completion_criteria": ["Listed execution-only wrappers are absent from source."],
    }

    execution_context._assert_no_source_local_execution_artifacts(
        task, Path("task.md"), cleanup_baselines={source: accepted_baseline}
    )

    historical.write_text("def test_recreated(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "recreate historical execution test"], cwd=source, check=True)
    with pytest.raises(SystemExit, match="source-local execution artifact"):
        execution_context._assert_no_source_local_execution_artifacts(
            task, Path("task.md"), cleanup_baselines={source: accepted_baseline}
        )

    task["target_files"] = ["tests/test_wor999_new_evidence.py"]
    with pytest.raises(SystemExit, match="source-local execution artifact"):
        execution_context._assert_no_source_local_execution_artifacts(
            task, Path("task.md"), cleanup_baselines={source: accepted_baseline}
        )


def test_execution_artifacts_resolve_to_workspace_root_outside_source_member(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "work-bundle-main"
    source.mkdir(parents=True)

    target = resolve_execution_artifact_path(
        workspace,
        execution_id="plan-20260908-001",
        artifact_path="evidence/task-004.json",
        source_members=[source],
    )

    assert target == workspace / "orchestration/executions/plan-20260908-001/evidence/task-004.json"
    assert not target.is_relative_to(source)


@pytest.mark.parametrize("artifact_path", ["../escape.json", "/tmp/escape.json", "."])
def test_execution_artifact_resolution_rejects_unsafe_paths(
    tmp_path: Path, artifact_path: str
) -> None:
    with pytest.raises(SystemExit, match="artifact path"):
        resolve_execution_artifact_path(
            tmp_path,
            execution_id="plan-001",
            artifact_path=artifact_path,
            source_members=[tmp_path / "source"],
        )


def test_execution_artifact_resolution_fails_when_workspace_output_is_inside_source(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit, match="source member"):
        resolve_execution_artifact_path(
            tmp_path,
            execution_id="plan-001",
            artifact_path="result.json",
            source_members=[tmp_path],
        )
