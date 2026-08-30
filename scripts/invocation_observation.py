"""Best-effort, privacy-safe observation for public WorkBundle script invocations."""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Callable, Collection, Sequence
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar


DISABLE_ENV = "WORK_BUNDLE_INVOCATION_LOG"
CONFIG_ROOT_ENV = "WB_CONFIG_ROOT"
NO_COMMAND = "__no_command__"
UNKNOWN_COMMAND = "__unknown__"
SCHEMA_VERSION = 1
_T = TypeVar("_T")


def extract_command(
    surface: str,
    argv: Sequence[str],
    recognized_commands: Collection[str],
) -> str:
    """Project argv to an allowlisted command without retaining arbitrary values."""
    if surface != "orch":
        if not argv or argv[0] in {"-h", "--help"}:
            return NO_COMMAND
        return argv[0] if argv[0] in recognized_commands else UNKNOWN_COMMAND

    index = 0
    while index < len(argv):
        token = argv[index]
        if token in {"-h", "--help"}:
            return NO_COMMAND
        if token == "--project-root":
            if index + 1 >= len(argv):
                return NO_COMMAND
            value = argv[index + 1]
            if value in {"-h", "--help"}:
                return NO_COMMAND
            if value.startswith("-"):
                return UNKNOWN_COMMAND
            index += 2
            continue
        if token.startswith("--project-root="):
            index += 1
            continue
        if token.startswith("-"):
            return UNKNOWN_COMMAND
        return token if token in recognized_commands else UNKNOWN_COMMAND
    return NO_COMMAND


def _database_path() -> Path:
    configured = os.environ.get(CONFIG_ROOT_ENV)
    root = Path(configured).expanduser() if configured else Path.home() / ".work-bundle"
    return root / "usage" / "invocations.sqlite3"


def _protect(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass


def _connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _protect(database.parent, 0o700)
    connection = sqlite3.connect(database, timeout=0.05)
    connection.execute("PRAGMA busy_timeout = 50")
    connection.execute("PRAGMA journal_mode = WAL")
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version not in {0, SCHEMA_VERSION}:
        raise sqlite3.DatabaseError(f"unsupported invocation schema version: {version}")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS invocation (
          id INTEGER PRIMARY KEY,
          started_at_utc TEXT NOT NULL,
          surface TEXT NOT NULL,
          command TEXT NOT NULL,
          state TEXT NOT NULL,
          exit_code INTEGER,
          duration_ms INTEGER
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS invocation_surface_command_started
        ON invocation(surface, command, started_at_utc)
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS invocation_state ON invocation(state)"
    )
    if version == 0:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.commit()
    _protect(database, 0o600)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{database}{suffix}")
        if sidecar.exists():
            _protect(sidecar, 0o600)
    return connection


def _begin(surface: str, command: str) -> tuple[Path, int] | None:
    if os.environ.get(DISABLE_ENV) == "0":
        return None
    try:
        database = _database_path()
        with closing(_connect(database)) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO invocation(started_at_utc, surface, command, state)
                    VALUES (?, ?, ?, ?)
                    """,
                    (datetime.now(UTC).isoformat(), surface, command, "started"),
                )
                row_id = int(cursor.lastrowid)
        return database, row_id
    except (OSError, RuntimeError, sqlite3.Error):
        return None


def _finish(
    token: tuple[Path, int] | None,
    *,
    state: str,
    exit_code: int,
    started: float,
) -> None:
    if token is None:
        return
    database, row_id = token
    duration_ms = max(0, round((time.monotonic() - started) * 1000))
    try:
        with closing(_connect(database)) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE invocation
                    SET state = ?, exit_code = ?, duration_ms = ?
                    WHERE id = ?
                    """,
                    (state, exit_code, duration_ms, row_id),
                )
    except (OSError, sqlite3.Error):
        pass


def _system_exit_code(code: object) -> int:
    if code is None:
        return 0
    return code if isinstance(code, int) else 1


def invoke_observed(
    surface: str,
    argv: Sequence[str],
    recognized_commands: Collection[str],
    dispatch: Callable[[], _T],
) -> _T:
    """Invoke dispatch while recording a lower-bound local lifecycle row."""
    command = extract_command(surface, argv, recognized_commands)
    started = time.monotonic()
    token = _begin(surface, command)
    try:
        result = dispatch()
    except SystemExit as exc:
        exit_code = _system_exit_code(exc.code)
        _finish(
            token,
            state="completed" if exit_code == 0 else "failed",
            exit_code=exit_code,
            started=started,
        )
        raise
    except BaseException:
        _finish(token, state="failed", exit_code=1, started=started)
        raise
    exit_code = result if isinstance(result, int) else 0
    _finish(
        token,
        state="completed" if exit_code == 0 else "failed",
        exit_code=exit_code,
        started=started,
    )
    return result
