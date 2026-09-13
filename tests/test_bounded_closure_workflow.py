from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = (
    REPO_ROOT / "scripts/orch.py",
    REPO_ROOT / "scripts/wb.py",
)
ORCHESTRATION = REPO_ROOT / "scripts/orchestration"
if str(ORCHESTRATION) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATION))

import bounded_closure  # noqa: E402


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _run(
    entrypoint: Path,
    cwd: Path,
    *arguments: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(entrypoint), *arguments],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _write_workspace(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str], Path, str]:
    workspace = tmp_path / "workspace"
    member = workspace / "repositories/product-main"
    worktree = tmp_path / "execution-worktree"
    member.mkdir(parents=True)
    worktree.mkdir()

    original_blocker = workspace / ".work-bundle/orchestration/spec/active/spec-wor113.md"
    original_blocker.parent.mkdir(parents=True)
    original_blocker.write_text("# WOR-113 unresolved\n", encoding="utf-8")
    metadata = {
        "metadata_version": 4,
        "workspace": {"id": "workspace-test", "mode": "multi-repository"},
        "orchestration_control": {
            "schema_version": 1,
            "post_execution_review_round_limit": 5,
            "blockers": [
                {
                    "id": "BLOCK-WOR113",
                    "status": "active",
                    "origin_plan": "plan-wor113",
                    "origin_spec": "spec-wor113",
                    "specification": original_blocker.relative_to(workspace).as_posix(),
                }
            ],
            "implementation_exemptions": [
                {
                    "flow_id": "plan-flow",
                    "blocker_id": "BLOCK-WOR113",
                    "status": "active",
                }
            ],
            "unrelated_extension": {"preserve": ["newer", "state"]},
        },
    }
    metadata_path = workspace / ".work-bundle/project.yaml"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    backup = tmp_path / "pre-exemption-project.yaml"
    original = {
        **metadata,
        "orchestration_control": {
            **metadata["orchestration_control"],
            "implementation_exemptions": [],
        },
    }
    backup.write_text(yaml.safe_dump(original, sort_keys=False), encoding="utf-8")
    backup_sha256 = hashlib.sha256(backup.read_bytes()).hexdigest()

    active_spec = workspace / ".work-bundle/orchestration/spec/active"
    active_plan = workspace / ".work-bundle/orchestration/plan/active"
    (active_plan / "plan-flow").mkdir(parents=True)
    (active_spec / "spec-origin.md").write_text(
        "---\nid: spec-origin\nstatus: verified\n---\n# Origin specification\n",
        encoding="utf-8",
    )
    residual = active_spec / "spec-residual.md"
    residual.write_text(
        "---\nid: spec-residual\nstatus: active\n---\n"
        "# Residual findings\n\n- Product acceptance remains unresolved.\n",
        encoding="utf-8",
    )
    (active_plan / "plan-origin.md").write_text(
        "---\nid: plan-flow\nstatus: In progress\n---\n# Origin plan\n",
        encoding="utf-8",
    )
    (active_plan / "plan-flow/task-001.md").write_text(
        "---\nid: task-001\nplan_id: plan-flow\nphase_id: phase-001\n"
        "status: Completed\n---\n# Terminal task\n",
        encoding="utf-8",
    )

    source = tmp_path / "clean-source"
    source.mkdir()
    subprocess.run(["git", "-C", str(source), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(source), "config", "user.name", "Test"], check=True
    )
    (source / "product.txt").write_text("unresolved\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "baseline"], check=True)
    baseline = {
        "repository_id": "product-main",
        "project_root": str(source),
        "commit": _git(source, "rev-parse", "HEAD"),
        "tree": _git(source, "rev-parse", "HEAD^{tree}"),
    }

    config = tmp_path / "config"
    registry = config / "registry/projects.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        yaml.safe_dump(
            {
                "device_bindings": {
                    "workspace-test": {
                        "workspace_root": str(workspace),
                        "repositories": [
                            {
                                "repository_id": "product-main",
                                "project_root": str(member),
                            }
                        ],
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (config / "bootstrap.yaml").write_text(
        yaml.safe_dump({"project_registry": str(registry)}, sort_keys=False),
        encoding="utf-8",
    )
    return workspace, member, worktree, baseline, backup, backup_sha256


def test_two_stage_public_workflow_exhausts_finalizes_restores_and_blocks_without_side_effects(
    tmp_path: Path,
) -> None:
    workspace, member, worktree, baseline, backup, backup_sha256 = _write_workspace(
        tmp_path
    )
    env = {**os.environ, "WB_CONFIG_ROOT": str(tmp_path / "config")}
    target = {
        "artifact_id": "plan-flow",
        "revision": "final",
        "sha256": hashlib.sha256(b"final-target").hexdigest(),
        "source_tree": baseline["tree"],
    }
    attempts = [{"execution_id": "executor-1", "state": "completed"}]

    for number in range(1, 6):
        begin = _run(
            ENTRYPOINTS[(number - 1) % 2],
            member,
            "begin-review-round",
            "--project-root",
            str(member),
            "--flow-id",
            "plan-flow",
            "--request-id",
            f"round-request-{number}",
            "--review-id",
            f"review-double-{number}",
            "--target-identity",
            json.dumps({**target, "revision": str(number)}),
            "--executor-attempts",
            json.dumps(attempts),
            "--known-missing-evidence",
            json.dumps(["integrated_product_acceptance"]),
            env=env,
        )
        assert begin.returncode == 0, begin.stderr
        reserved = json.loads(begin.stdout)
        complete = _run(
            ENTRYPOINTS[number % 2],
            workspace,
            "complete-review-round",
            "--project-root",
            str(workspace),
            "--flow-id",
            "plan-flow",
            "--round-id",
            reserved["round_id"],
            "--outcome",
            "blocked",
            "--audit-block",
            json.dumps(
                {
                    "code": "reviewer-double-residual",
                    "round": number,
                    "missing": ["integrated_product_acceptance"],
                }
            ),
            env=env,
        )
        assert complete.returncode == 0, complete.stderr

    before_refusal = _snapshot(workspace)
    sixth = _run(
        ENTRYPOINTS[0],
        workspace,
        "begin-review-round",
        "--project-root",
        str(workspace),
        "--flow-id",
        "plan-flow",
        "--request-id",
        "round-request-6",
        "--review-id",
        "review-double-6",
        "--target-identity",
        json.dumps(target),
        "--executor-attempts",
        json.dumps(attempts),
        "--known-missing-evidence",
        json.dumps(["integrated_product_acceptance"]),
        env=env,
    )
    assert sixth.returncode != 0
    assert "WB_ORCHESTRATION_FINALIZATION_REQUIRED" in sixth.stderr
    assert _snapshot(workspace) == before_refusal

    finalized = _run(
        ENTRYPOINTS[1],
        worktree,
        "finalize-with-blockers",
        "--project-root",
        str(workspace),
        "--flow-id",
        "plan-flow",
        "--request-id",
        "finalize-request-1",
        "--blocker-id",
        "BLOCK-plan-flow",
        "--residual-spec-id",
        "spec-residual",
        "--residual-spec",
        str(workspace / ".work-bundle/orchestration/spec/active/spec-residual.md"),
        "--origin-spec-id",
        "spec-origin",
        "--origin-plan-id",
        "plan-flow",
        "--source-baselines",
        json.dumps([baseline]),
        "--knowledge-return",
        json.dumps({"status": "not-needed", "evidence_ref": None}),
        env=env,
    )
    assert finalized.returncode == 0, finalized.stderr
    result = json.loads(finalized.stdout)
    assert result["outcome"] == "closed_with_blockers"
    assert result["source_baselines"] == [
        {key: baseline[key] for key in ("repository_id", "commit", "tree")}
    ]
    assert not (workspace / ".work-bundle/orchestration/spec/active/spec-origin.md").exists()
    assert (workspace / ".work-bundle/orchestration/spec/archived/spec-origin.md").is_file()
    assert not (workspace / ".work-bundle/orchestration/plan/active/plan-origin.md").exists()
    assert (workspace / ".work-bundle/orchestration/plan/archived/plan-origin.md").is_file()
    assert not (workspace / ".work-bundle/orchestration/reviews").exists()

    metadata_path = workspace / ".work-bundle/project.yaml"
    current = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    other_spec = workspace / ".work-bundle/orchestration/spec/active/spec-other.md"
    other_spec.write_text("# Other unresolved work\n", encoding="utf-8")
    current["orchestration_control"]["blockers"].append(
        {
            "id": "BLOCK-OTHER",
            "status": "active",
            "origin_plan": "plan-other",
            "specification": other_spec.relative_to(workspace).as_posix(),
        }
    )
    current["orchestration_control"]["unrelated_extension"] = {
        "preserve": ["newer", "state", "after-finalization"]
    }
    metadata_path.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")

    assert hashlib.sha256(backup.read_bytes()).hexdigest() == backup_sha256
    assert bounded_closure.restore_implementation_exception(
        workspace,
        backup_path=backup,
        backup_sha256=backup_sha256,
        flow_id="plan-flow",
        blocker_id="BLOCK-WOR113",
    )
    restored = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))[
        "orchestration_control"
    ]
    assert restored["implementation_exemptions"] == []
    assert {blocker["id"] for blocker in restored["blockers"]} == {
        "BLOCK-WOR113",
        "BLOCK-plan-flow",
        "BLOCK-OTHER",
    }
    assert restored["unrelated_extension"] == {
        "preserve": ["newer", "state", "after-finalization"]
    }
    restored["blockers"].sort(
        key=lambda blocker: blocker["id"] != "BLOCK-WOR113"
    )
    current = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    current["orchestration_control"] = restored
    metadata_path.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")

    candidate = tmp_path / "candidate.md"
    candidate.write_text("# Must not be consumed\n", encoding="utf-8")
    contexts = (
        (ENTRYPOINTS[0], workspace, ("--project-root", str(workspace))),
        (ENTRYPOINTS[0], member, ("--project-root", str(member))),
        (ENTRYPOINTS[0], worktree, ("--project-root", str(workspace))),
    )
    before_denials = _snapshot(workspace)
    for index, (entrypoint, cwd, locator) in enumerate(contexts, start=1):
        denied = _run(
            entrypoint,
            cwd,
            "write-spec",
            *locator,
            "--title",
            "Denied candidate",
            "--purpose",
            "prove pre-side-effect refusal",
            "--component",
            "test",
            "--content-file",
            str(candidate),
            "--id",
            f"spec-denied-{index}",
            env=env,
        )
        assert denied.returncode != 0
        assert all(
            token in denied.stderr
            for token in (
                "WB_ORCHESTRATION_ADMISSION_BLOCKED",
                str(metadata_path),
                "BLOCK-WOR113",
                "spec-wor113.md",
                "orch-bounded-closure",
            )
        ), denied.stderr
        assert _snapshot(workspace) == before_denials

    for index, (cwd, locator) in enumerate(
        (
            (workspace, ("--project-root", str(workspace))),
            (member, ("--project-root", str(member))),
            (worktree, ("--project-root", str(workspace))),
        ),
        start=1,
    ):
        denied = _run(
            ENTRYPOINTS[1],
            cwd,
            "begin-review-round",
            *locator,
            "--flow-id",
            f"unrelated-flow-{index}",
            "--request-id",
            f"denied-round-request-{index}",
            "--review-id",
            f"denied-review-double-{index}",
            "--target-identity",
            json.dumps(target),
            "--executor-attempts",
            json.dumps(attempts),
            "--known-missing-evidence",
            json.dumps(["integrated_product_acceptance"]),
            env=env,
        )
        assert denied.returncode != 0
        assert all(
            token in denied.stderr
            for token in (
                "WB_ORCHESTRATION_ADMISSION_BLOCKED",
                str(metadata_path),
                "BLOCK-WOR113",
                "spec-wor113.md",
                "orch-bounded-closure",
            )
        ), denied.stderr
        assert _snapshot(workspace) == before_denials
