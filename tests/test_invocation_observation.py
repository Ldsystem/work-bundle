from __future__ import annotations

import importlib.util
import ast
import os
import sqlite3
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_observation():
    return load_module("invocation_observation_test", SCRIPTS / "invocation_observation.py")


def rows(config_root: Path) -> list[tuple[object, ...]]:
    database = config_root / "usage" / "invocations.sqlite3"
    with sqlite3.connect(database) as connection:
        return connection.execute(
            "SELECT surface, command, state, exit_code, duration_ms FROM invocation ORDER BY id"
        ).fetchall()


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("WORK_BUNDLE_INVOCATION_LOG", "1")
    monkeypatch.setenv("WB_CONFIG_ROOT", str(tmp_path))
    return tmp_path


def test_surface_aware_command_extraction_never_persists_option_values() -> None:
    observation = load_observation()
    recognized = {"doctor", "state"}

    assert observation.extract_command("wb", ["doctor"], recognized) == "doctor"
    assert observation.extract_command("ks", [], recognized) == "__no_command__"
    assert observation.extract_command("wb", ["--invented", "/secret"], recognized) == "__unknown__"
    assert observation.extract_command(
        "orch", ["--project-root", "/private/path", "doctor"], recognized
    ) == "doctor"
    assert observation.extract_command(
        "orch", ["--project-root=/private/path", "doctor"], recognized
    ) == "doctor"
    assert observation.extract_command("orch", ["--help", "doctor"], recognized) == "__no_command__"
    assert observation.extract_command("orch", ["--project", "/secret", "doctor"], recognized) == "__unknown__"


def test_success_creates_v1_schema_and_privacy_safe_row(enabled: Path) -> None:
    observation = load_observation()
    secret = "/private/a-secret-path"

    result = observation.invoke_observed("orch", ["doctor", secret], {"doctor"}, lambda: 0)

    assert result == 0
    assert rows(enabled) == [("orch", "doctor", "completed", 0, rows(enabled)[0][4])]
    assert isinstance(rows(enabled)[0][4], int) and rows(enabled)[0][4] >= 0
    database = enabled / "usage" / "invocations.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        columns = [item[1] for item in connection.execute("PRAGMA table_info(invocation)")]
        assert columns == ["id", "started_at_utc", "surface", "command", "state", "exit_code", "duration_ms"]
        indexes = {item[1] for item in connection.execute("PRAGMA index_list(invocation)")}
        assert {"invocation_surface_command_started", "invocation_state"} <= indexes
    assert secret.encode() not in database.read_bytes()
    if os.name != "nt":
        assert stat.S_IMODE((enabled / "usage").stat().st_mode) == 0o700
        assert stat.S_IMODE(database.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("code", "state", "stored_code"),
    [(None, "completed", 0), (0, "completed", 0), (2, "failed", 2), ("bad", "failed", 1)],
)
def test_system_exit_is_classified_and_reraised_literally(
    enabled: Path, code: object, state: str, stored_code: int
) -> None:
    observation = load_observation()
    original = SystemExit(code)

    def dispatch() -> int:
        raise original

    with pytest.raises(SystemExit) as caught:
        observation.invoke_observed("wb", ["doctor"], {"doctor"}, dispatch)

    assert caught.value is original
    assert rows(enabled)[0][2:4] == (state, stored_code)


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyboardInterrupt()])
def test_base_exceptions_fail_and_retain_identity(enabled: Path, error: BaseException) -> None:
    observation = load_observation()

    def dispatch() -> int:
        raise error

    with pytest.raises(BaseException) as caught:
        observation.invoke_observed("ks", ["doctor"], {"doctor"}, dispatch)

    assert caught.value is error
    assert rows(enabled)[0][2:4] == ("failed", 1)


def test_nonzero_return_is_failed(enabled: Path) -> None:
    observation = load_observation()
    assert observation.invoke_observed("wb", ["doctor"], {"doctor"}, lambda: 3) == 3
    assert rows(enabled)[0][2:4] == ("failed", 3)


def test_exact_zero_is_only_disable_value(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    observation = load_observation()
    monkeypatch.setenv("WB_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("WORK_BUNDLE_INVOCATION_LOG", "0")
    assert observation.invoke_observed("wb", ["doctor"], {"doctor"}, lambda: 0) == 0
    assert not (tmp_path / "usage").exists()

    monkeypatch.setenv("WORK_BUNDLE_INVOCATION_LOG", "false")
    assert observation.invoke_observed("wb", ["doctor"], {"doctor"}, lambda: 0) == 0
    assert rows(tmp_path)[0][1] == "doctor"


def test_database_failure_is_silent_and_does_not_change_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    observation = load_observation()
    blocked_root = tmp_path / "not-a-directory"
    blocked_root.write_text("occupied", encoding="utf-8")
    monkeypatch.setenv("WORK_BUNDLE_INVOCATION_LOG", "1")
    monkeypatch.setenv("WB_CONFIG_ROOT", str(blocked_root))

    assert observation.invoke_observed("wb", ["doctor"], {"doctor"}, lambda: 7) == 7
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(("filename", "surface"), [("wb.py", "wb"), ("orch.py", "orch")])
def test_public_wrappers_observe_once(
    enabled: Path, monkeypatch: pytest.MonkeyPatch, filename: str, surface: str
) -> None:
    module = load_module(f"{surface}_wrapper_test", SCRIPTS / filename)
    dispatcher = SimpleNamespace(main=lambda: 0, RECOGNIZED_COMMANDS=frozenset({"doctor"}))
    monkeypatch.setattr(module, "_load_dispatcher", lambda: dispatcher)
    monkeypatch.setattr(sys, "argv", [filename, "doctor"])

    assert module.main() == 0
    assert rows(enabled) == [(surface, "doctor", "completed", 0, rows(enabled)[0][4])]


def test_ks_logs_only_after_runtime_readiness(enabled: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("ks_wrapper_test", SCRIPTS / "ks.py")
    dispatcher = SimpleNamespace(main=lambda: 0, RECOGNIZED_COMMANDS=frozenset({"doctor"}))
    monkeypatch.setattr(module, "_load_dispatcher", lambda: dispatcher)
    monkeypatch.setattr(sys, "argv", ["ks.py", "doctor"])
    monkeypatch.setattr(module, "_ensure_managed_runtime", lambda: (False, "not ready"))

    assert module.main() == 2
    assert not (enabled / "usage").exists()

    monkeypatch.setattr(module, "_ensure_managed_runtime", lambda: (True, None))
    assert module.main() == 0
    assert len(rows(enabled)) == 1


def test_recognized_vocabulary_is_exact() -> None:
    wb = (SCRIPTS / "work-bundle" / "dispatcher.py").read_text(encoding="utf-8")
    for command in (
        "execution-workspace-prepare",
        "execution-workspace-status",
        "execution-workspace-mark-terminal",
        "execution-workspace-cleanup-owned",
        "execution-workspace-doctor-stale",
    ):
        assert repr(command) in wb
    assert "violation-list" not in wb


@pytest.mark.parametrize(
    "path",
    [SCRIPTS / "keep-summarizing" / "dispatcher.py", SCRIPTS / "orchestration" / "dispatcher.py"],
)
def test_subparser_vocabulary_matches_exported_recognized_set(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    routed = {
        call.args[0].value
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "add_parser"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    }
    exported: set[str] | None = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "RECOGNIZED_COMMANDS" for target in node.targets):
            continue
        assert isinstance(node.value, ast.Call) and node.value.args
        assert isinstance(node.value.args[0], ast.Set)
        exported = {
            item.value
            for item in node.value.args[0].elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }
    assert exported == routed
