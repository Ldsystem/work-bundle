from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_wrapper(name: str):
    path = REPO_ROOT / f"scripts/{name}.py"
    spec = importlib.util.spec_from_file_location(f"runtime_wrapper_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["orch", "wb"])
def test_public_wrapper_declares_same_pinned_runtime(name: str) -> None:
    text = (REPO_ROOT / f"scripts/{name}.py").read_text(encoding="utf-8")
    assert '# requires-python = ">=3.13"' in text
    assert '"pyyaml==6.0.3"' in text
    assert '"jsonschema==4.25.1"' in text
    wrapper = load_wrapper(name)
    assert wrapper.RUNTIME_DEPENDENCIES == (
        ("yaml", "pyyaml"),
        ("jsonschema", "jsonschema"),
    )


def test_keep_summarizing_wrapper_declares_shared_infrastructure_dependencies() -> None:
    text = (REPO_ROOT / "scripts/ks.py").read_text(encoding="utf-8")
    assert '"pyyaml==6.0.3"' in text
    assert '"jsonschema==4.25.1"' in text
    wrapper = load_wrapper("ks")
    assert ("yaml", "pyyaml") in wrapper.RUNTIME_DEPENDENCIES
    assert ("jsonschema", "jsonschema") in wrapper.RUNTIME_DEPENDENCIES


@pytest.mark.parametrize("name", ["orch", "wb"])
def test_missing_uv_is_typed_and_actionable(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    wrapper = load_wrapper(name)
    monkeypatch.setattr(wrapper, "_missing_runtime_dependencies", lambda: ["yaml", "jsonschema"])
    monkeypatch.setattr(wrapper.shutil, "which", lambda _name: None)
    ready, failure = wrapper._ensure_managed_runtime(argv=[f"{name}.py", "--help"], environ={})
    assert ready is False
    assert failure is not None
    assert failure.startswith("WB_RUNTIME_DEPENDENCY_UNAVAILABLE:")
    assert "install uv" in failure


@pytest.mark.parametrize("name", ["orch", "wb"])
def test_recursion_guard_returns_typed_failure(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    wrapper = load_wrapper(name)
    monkeypatch.setattr(wrapper, "_missing_runtime_dependencies", lambda: ["yaml"])
    ready, failure = wrapper._ensure_managed_runtime(
        argv=[f"{name}.py", "--help"],
        environ={wrapper.UV_REEXEC_ENV: "1"},
    )
    assert ready is False
    assert failure is not None and "uv could not hydrate" in failure


@pytest.mark.parametrize("name", ["orch", "wb"])
def test_uv_reexec_uses_current_wrapper_and_preserves_arguments(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    wrapper = load_wrapper(name)
    monkeypatch.setattr(wrapper, "_missing_runtime_dependencies", lambda: ["yaml"])
    monkeypatch.setattr(wrapper.shutil, "which", lambda _name: "/opt/test/uv")
    observed: dict[str, object] = {}

    def fake_execve(executable: str, argv: list[str], environment: dict[str, str]) -> None:
        observed.update(executable=executable, argv=argv, environment=environment)
        raise RuntimeError("stop")

    monkeypatch.setattr(wrapper.os, "execve", fake_execve)
    with pytest.raises(RuntimeError, match="stop"):
        wrapper._ensure_managed_runtime(
            argv=[f"{name}.py", "doctor", "--project-root", "/tmp/example"], environ={"KEEP": "yes"}
        )
    assert observed["executable"] == "/opt/test/uv"
    assert observed["argv"] == [
        "/opt/test/uv",
        "run",
        str((REPO_ROOT / f"scripts/{name}.py").resolve()),
        "doctor",
        "--project-root",
        "/tmp/example",
    ]
    assert observed["environment"][wrapper.UV_REEXEC_ENV] == "1"
    assert observed["environment"]["KEEP"] == "yes"


@pytest.mark.parametrize(
    ("command", "failure_code"),
    [
        ("provision-member", "WB_V3_MEMBER_COMMAND_RETIRED"),
        ("cleanup-member", "WB_V3_MEMBER_COMMAND_RETIRED"),
        ("migrate-to-multi-repository", "WB_TOPOLOGY_MIGRATION_COMMAND_RETIRED"),
    ],
)
def test_v3_mutating_public_commands_are_typed_refusals(
    tmp_path: Path, command: str, failure_code: str
) -> None:
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path)
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), command],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["failure_code"] == failure_code


def test_removed_wor107_migration_stop_route_is_not_publicly_dispatchable(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path)
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), "assert-migration-stop"],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "unknown command: assert-migration-stop" in completed.stderr
