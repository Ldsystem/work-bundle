from __future__ import annotations

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
