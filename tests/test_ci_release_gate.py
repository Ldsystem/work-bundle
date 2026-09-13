from __future__ import annotations

import runpy
import re
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CI_ENTRY = REPO_ROOT / "bin" / "work-bundle-ci"


def _gate_api():
    return runpy.run_path(str(CI_ENTRY))["run_release_gate"]


def test_release_gate_reports_start_before_running_each_module() -> None:
    events = []

    def run(command, **kwargs):
        events.append(("run", str(command[-1])))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    _gate_api()(REPO_ROOT, python_executable="/python",
                test_files=[Path("tests/test_a.py")], run_command=run,
                emit=lambda line: events.append(("output", line)))

    assert events.index(("output", "WB_CI_MODULE START tests/test_a.py")) < events.index(("run", "tests/test_a.py"))


def test_default_ci_output_flushes_immediately(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: calls.append((args, kwargs)))
    _gate_api()(REPO_ROOT, python_executable="/python", test_files=[],
                run_command=lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="", stderr=""))
    assert calls
    assert all(kwargs.get("flush") is True for _args, kwargs in calls)


def test_workflow_cache_uses_pinned_dependency_owner_without_reducing_matrix() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["deterministic"]
    assert job["strategy"]["matrix"]["os"] == ["ubuntu-latest", "macos-latest"]
    setup = next(step for step in job["steps"] if step.get("uses", "").startswith("astral-sh/setup-uv@"))
    assert setup["with"]["enable-cache"] is True
    assert setup["with"]["cache-dependency-glob"] == "bin/work-bundle-ci"


def test_release_gate_continues_after_early_module_failure() -> None:
    commands: list[list[str]] = []
    output: list[str] = []

    def fake_run(command, **kwargs):
        argv = [str(item) for item in command]
        commands.append(argv)
        failed = argv[-1] == "tests/test_a.py"
        return subprocess.CompletedProcess(argv, 1 if failed else 0, stdout="early failure" if failed else "", stderr="")

    result = _gate_api()(
        REPO_ROOT,
        python_executable="/python",
        test_files=[Path("tests/test_a.py"), Path("tests/test_b.py"), Path("tests/test_c.py")],
        run_command=fake_run,
        emit=output.append,
    )

    assert [command[-1] for command in commands[:3]] == [
        "tests/test_a.py",
        "tests/test_b.py",
        "tests/test_c.py",
    ]
    assert commands[3][-1] == "validate"
    assert result["exit_code"] == 1
    assert result["failed_modules"] == ["tests/test_a.py"]
    assert "WB_CI_MODULE PASS tests/test_c.py" in output


def test_release_gate_inputs_are_tracked_and_execution_independent() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "tests/test_*.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    discovered = sorted(path.relative_to(REPO_ROOT).as_posix() for path in (REPO_ROOT / "tests").glob("test_*.py"))

    assert tracked == discovered
    for path in [CI_ENTRY, REPO_ROOT / "bin" / "work-bundle-skill", REPO_ROOT / ".github" / "workflows" / "ci.yml"]:
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", path.relative_to(REPO_ROOT).as_posix()],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    assert ".work-bundle" not in CI_ENTRY.read_text(encoding="utf-8")
    assert not (REPO_ROOT / "evals" / "wor105").exists()
    assert not (REPO_ROOT / "evals" / "wor108").exists()
    assert not any(re.match(r"test_(?:wor|issue)[-_]?\d+", Path(path).stem) for path in discovered)


def test_release_gate_does_not_read_workspace_execution_evidence() -> None:
    source = CI_ENTRY.read_text(encoding="utf-8")
    assert "orchestration/executions" not in source
    assert "evals/wor" not in source


def test_release_gate_collects_test_and_skill_failures() -> None:
    commands: list[list[str]] = []
    output: list[str] = []

    def fake_run(command, **kwargs):
        argv = [str(item) for item in command]
        commands.append(argv)
        is_skill = argv[-1] == "validate"
        return subprocess.CompletedProcess(
            argv,
            2 if is_skill else 1,
            stdout="skill failure" if is_skill else "test failure",
            stderr="",
        )

    result = _gate_api()(
        REPO_ROOT,
        python_executable="/python",
        test_files=[Path("tests/test_failure.py")],
        run_command=fake_run,
        emit=output.append,
    )

    assert len(commands) == 2
    assert result == {
        "exit_code": 1,
        "modules": ["tests/test_failure.py"],
        "failed_modules": ["tests/test_failure.py"],
        "skills": "failed",
    }
    assert "WB_CI_MODULE FAIL tests/test_failure.py" in output
    assert "WB_CI_SKILLS FAIL" in output
    assert "WB_CI_RESULT FAIL" in output


def test_workflow_delegates_to_canonical_release_gate() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    entry = CI_ENTRY.read_text(encoding="utf-8")

    assert workflow.count("run: bin/work-bundle-ci") == 1
    assert "python -c" not in workflow
    assert "Validate skill packages" not in workflow
    for pin in [
        '"3.13"',
        '"pytest==9.1.1"',
        '"pyyaml==6.0.3"',
        '"sqlite-vec==0.1.9"',
        '"fastembed==0.8.0"',
    ]:
        assert pin in entry


def test_workflow_uses_default_checkout_history_for_current_project_tests() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deterministic"]["steps"]
    checkout = [step for step in steps if step.get("uses", "").startswith("actions/checkout@")]

    assert len(checkout) == 1
    assert "with" not in checkout[0]
