from __future__ import annotations

import errno
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

import platform_runtime  # noqa: E402


def _hold_shared(path: str, ready, release) -> None:
    with open(path, "a+b") as stream:
        with platform_runtime.blocking_file_lock(stream, shared=True):
            ready.set()
            release.wait()


def _hold_exclusive(path: str, acquired) -> None:
    with open(path, "a+b") as stream:
        with platform_runtime.blocking_file_lock(stream):
            acquired.set()


def test_lock_path_input_owns_and_closes_opened_stream(monkeypatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "owned.lock"
    opened = []

    def open_lock_path(path):
        stream = open(path, "a+b")
        opened.append(stream)
        return stream

    monkeypatch.setattr(platform_runtime, "_open_lock_path", open_lock_path, raising=False)
    with platform_runtime.blocking_file_lock(lock_path, shared=True):
        assert opened and not opened[0].closed

    assert opened[0].closed
    assert lock_path.is_file()


def test_lock_path_input_closes_owned_stream_on_body_error(monkeypatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "owned-error.lock"
    opened = []

    def open_lock_path(path):
        stream = open(path, "a+b")
        opened.append(stream)
        return stream

    monkeypatch.setattr(platform_runtime, "_open_lock_path", open_lock_path, raising=False)
    with pytest.raises(RuntimeError, match="body failed"):
        with platform_runtime.blocking_file_lock(lock_path):
            raise RuntimeError("body failed")

    assert opened[0].closed


def test_lock_path_input_closes_owned_stream_when_acquisition_fails(
    monkeypatch, tmp_path: Path
) -> None:
    lock_path = tmp_path / "owned-acquisition-error.lock"
    opened = []

    def open_lock_path(path):
        stream = open(path, "a+b")
        opened.append(stream)
        return stream

    class FakeMsvcrt:
        LK_NBLCK = 1

        @staticmethod
        def locking(_descriptor: int, _mode: int, _length: int) -> None:
            raise OSError(errno.EIO, "acquisition failed")

    monkeypatch.setattr(platform_runtime, "_open_lock_path", open_lock_path)
    monkeypatch.setattr(platform_runtime, "_IS_WINDOWS", True)
    monkeypatch.setattr(platform_runtime, "_MSVCRT", FakeMsvcrt)
    with pytest.raises(OSError, match="acquisition failed"):
        with platform_runtime.blocking_file_lock(lock_path):
            pass

    assert opened[0].closed


@pytest.mark.parametrize("body_fails", [False, True])
def test_lock_preserves_caller_owned_stream(tmp_path: Path, body_fails: bool) -> None:
    with (tmp_path / "caller.lock").open("a+b") as stream:
        if body_fails:
            with pytest.raises(RuntimeError, match="body failed"):
                with platform_runtime.blocking_file_lock(stream):
                    raise RuntimeError("body failed")
        else:
            with platform_runtime.blocking_file_lock(stream):
                pass
        assert not stream.closed


def test_lock_preserves_caller_owned_stream_when_acquisition_fails(
    monkeypatch, tmp_path: Path
) -> None:
    class FakeMsvcrt:
        LK_NBLCK = 1

        @staticmethod
        def locking(_descriptor: int, _mode: int, _length: int) -> None:
            raise OSError(errno.EIO, "acquisition failed")

    monkeypatch.setattr(platform_runtime, "_IS_WINDOWS", True)
    monkeypatch.setattr(platform_runtime, "_MSVCRT", FakeMsvcrt)
    with (tmp_path / "caller-acquisition-error.lock").open("a+b") as stream:
        with pytest.raises(OSError, match="acquisition failed"):
            with platform_runtime.blocking_file_lock(stream):
                pass
        assert not stream.closed


@pytest.mark.skipif(os.name == "nt", reason="POSIX shared-lock behavior")
def test_posix_shared_readers_do_not_block_each_other(tmp_path: Path) -> None:
    lock_path = tmp_path / "shared.lock"
    first_ready = multiprocessing.Event()
    second_ready = multiprocessing.Event()
    release = multiprocessing.Event()
    first = multiprocessing.Process(target=_hold_shared, args=(str(lock_path), first_ready, release))
    second = multiprocessing.Process(target=_hold_shared, args=(str(lock_path), second_ready, release))
    first.start()
    second.start()
    try:
        assert first_ready.wait(2)
        assert second_ready.wait(2)
    finally:
        release.set()
        first.join(5)
        second.join(5)
    assert first.exitcode == second.exitcode == 0


@pytest.mark.skipif(os.name == "nt", reason="POSIX shared-lock behavior")
def test_posix_exclusive_writer_waits_for_shared_reader(tmp_path: Path) -> None:
    lock_path = tmp_path / "exclusive.lock"
    shared_ready = multiprocessing.Event()
    release_shared = multiprocessing.Event()
    exclusive_acquired = multiprocessing.Event()
    reader = multiprocessing.Process(
        target=_hold_shared, args=(str(lock_path), shared_ready, release_shared)
    )
    writer = multiprocessing.Process(
        target=_hold_exclusive, args=(str(lock_path), exclusive_acquired)
    )
    reader.start()
    try:
        assert shared_ready.wait(2)
        writer.start()
        assert not exclusive_acquired.wait(0.2)
        release_shared.set()
        assert exclusive_acquired.wait(2)
    finally:
        release_shared.set()
        reader.join(5)
        if writer.pid is not None:
            writer.join(5)
    assert reader.exitcode == writer.exitcode == 0


def test_windows_lock_retries_beyond_native_retry_window(monkeypatch, tmp_path: Path) -> None:
    attempts: list[int] = []

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(_descriptor: int, mode: int, _length: int) -> None:
            if mode == FakeMsvcrt.LK_NBLCK:
                attempts.append(mode)
                if len(attempts) <= 12:
                    raise OSError(13, "locked")

    monkeypatch.setattr(platform_runtime, "_IS_WINDOWS", True)
    monkeypatch.setattr(platform_runtime, "_MSVCRT", FakeMsvcrt)
    monkeypatch.setattr(platform_runtime.time, "sleep", lambda _seconds: None)
    with (tmp_path / "windows.lock").open("a+b") as stream:
        with platform_runtime.blocking_file_lock(stream, shared=True):
            pass

    assert len(attempts) == 13


def test_windows_lock_does_not_retry_resource_exhaustion(monkeypatch, tmp_path: Path) -> None:
    attempts = 0

    class ResourceExhausted(OSError):
        errno = errno.EACCES
        winerror = 36

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(_descriptor: int, mode: int, _length: int) -> None:
            nonlocal attempts
            if mode == FakeMsvcrt.LK_NBLCK:
                attempts += 1
                raise ResourceExhausted("resource exhaustion")

    monkeypatch.setattr(platform_runtime, "_IS_WINDOWS", True)
    monkeypatch.setattr(platform_runtime, "_MSVCRT", FakeMsvcrt)
    with (tmp_path / "windows.lock").open("a+b") as stream:
        with pytest.raises(ResourceExhausted):
            with platform_runtime.blocking_file_lock(stream):
                pass

    assert attempts == 1


@pytest.mark.parametrize("error_number", [errno.EAGAIN, errno.EDEADLK])
def test_windows_lock_does_not_retry_undocumented_errno(
    monkeypatch, tmp_path: Path, error_number: int
) -> None:
    attempts = 0

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(_descriptor: int, mode: int, _length: int) -> None:
            nonlocal attempts
            if mode != FakeMsvcrt.LK_NBLCK:
                return
            attempts += 1
            if attempts == 1:
                raise OSError(error_number, "not documented contention")
            raise AssertionError("undocumented errno was retried")

    monkeypatch.setattr(platform_runtime, "_IS_WINDOWS", True)
    monkeypatch.setattr(platform_runtime, "_MSVCRT", FakeMsvcrt)
    with (tmp_path / "windows.lock").open("a+b") as stream:
        with pytest.raises(OSError) as captured:
            with platform_runtime.blocking_file_lock(stream):
                pass

    assert captured.value.errno == error_number
    assert attempts == 1


@pytest.mark.parametrize("failing_seek_call", [3, 4])
def test_windows_lock_attempts_unlock_when_offset_restoration_fails(
    monkeypatch, tmp_path: Path, failing_seek_call: int
) -> None:
    lock_modes: list[int] = []

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(_descriptor: int, mode: int, _length: int) -> None:
            lock_modes.append(mode)

    real_lseek = platform_runtime.os.lseek
    seek_calls = 0

    def lseek(*args):
        nonlocal seek_calls
        seek_calls += 1
        if seek_calls == failing_seek_call:
            raise OSError(errno.EIO, "offset failure")
        return real_lseek(*args)

    monkeypatch.setattr(platform_runtime, "_IS_WINDOWS", True)
    monkeypatch.setattr(platform_runtime, "_MSVCRT", FakeMsvcrt)
    monkeypatch.setattr(platform_runtime.os, "lseek", lseek)
    with (tmp_path / "windows.lock").open("a+b") as stream:
        with pytest.raises(OSError, match="offset failure"):
            with platform_runtime.blocking_file_lock(stream):
                if failing_seek_call == 4:
                    pass

    assert lock_modes == [FakeMsvcrt.LK_NBLCK, FakeMsvcrt.LK_UNLCK]


@pytest.mark.skipif(os.name != "nt", reason="native Windows contention behavior")
def test_native_windows_contention_blocks_beyond_ten_seconds(tmp_path: Path) -> None:
    lock_path = tmp_path / "native-windows.lock"
    first_ready = multiprocessing.Event()
    release_first = multiprocessing.Event()
    second_acquired = multiprocessing.Event()
    first = multiprocessing.Process(
        target=_hold_shared, args=(str(lock_path), first_ready, release_first)
    )
    second = multiprocessing.Process(
        target=_hold_exclusive, args=(str(lock_path), second_acquired)
    )
    first.start()
    try:
        assert first_ready.wait(2)
        second.start()
        assert not second_acquired.wait(0.2)
        time.sleep(10.5)
        assert not second_acquired.is_set()
        release_first.set()
        assert second_acquired.wait(2)
    finally:
        release_first.set()
        first.join(5)
        if second.pid is not None:
            second.join(5)
    assert first.exitcode == second.exitcode == 0


def test_atomic_replace_does_not_fail_when_directory_sync_is_unsupported(
    monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "state.json"
    target.write_bytes(b"old")
    monkeypatch.setattr(platform_runtime, "_IS_WINDOWS", True)

    platform_runtime.atomic_replace_bytes(target, b"new", mode=0o600)

    assert target.read_bytes() == b"new"
    assert not list(tmp_path.glob(f".{target.name}.*"))


def test_atomic_replace_ignores_only_unsupported_mode_hardening(
    monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "state.json"
    monkeypatch.setattr(
        platform_runtime.os,
        "fchmod",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.ENOTSUP, "unsupported")),
    )

    platform_runtime.atomic_replace_bytes(target, b"new", mode=0o600)

    assert target.read_bytes() == b"new"


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory-sync branch")
def test_atomic_replace_ignores_unsupported_post_replace_directory_sync(
    monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "state.json"
    real_fsync = platform_runtime.os.fsync
    calls = 0

    def fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(errno.EINVAL, "directory fsync unsupported")
        real_fsync(descriptor)

    monkeypatch.setattr(platform_runtime.os, "fsync", fsync)
    platform_runtime.atomic_replace_bytes(target, b"new")

    assert target.read_bytes() == b"new"
    assert calls == 2


def test_atomic_replace_propagates_replace_failure_and_preserves_old_file(
    monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "state.json"
    target.write_bytes(b"old")
    monkeypatch.setattr(
        platform_runtime.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EIO, "replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        platform_runtime.atomic_replace_bytes(target, b"new")

    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob(f".{target.name}.*"))


def test_atomic_replace_closes_descriptor_when_mode_hardening_fails(
    monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "state.json"
    real_mkstemp = platform_runtime.tempfile.mkstemp
    real_close = platform_runtime.os.close
    descriptor = -1
    closed: list[int] = []

    def mkstemp(*args, **kwargs):
        nonlocal descriptor
        descriptor, name = real_mkstemp(*args, **kwargs)
        return descriptor, name

    def close(value: int) -> None:
        closed.append(value)
        real_close(value)

    monkeypatch.setattr(platform_runtime.tempfile, "mkstemp", mkstemp)
    monkeypatch.setattr(platform_runtime.os, "close", close)
    monkeypatch.setattr(
        platform_runtime.os,
        "fchmod",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EIO, "mode failed")),
    )

    with pytest.raises(OSError, match="mode failed"):
        platform_runtime.atomic_replace_bytes(target, b"new", mode=0o600)

    assert descriptor in closed
    assert not list(tmp_path.glob(f".{target.name}.*"))


def test_path_classifier_distinguishes_ordinary_symlink_junction_and_reparse(
    monkeypatch, tmp_path: Path
) -> None:
    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(ordinary, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    junction = tmp_path / "junction"
    junction.mkdir()
    reparse = tmp_path / "reparse"
    reparse.mkdir()

    assert platform_runtime.classify_path(ordinary) == platform_runtime.PathKind.ORDINARY
    assert platform_runtime.classify_path(link) == platform_runtime.PathKind.SYMLINK
    monkeypatch.setattr(platform_runtime, "_is_junction", lambda path: path == junction)
    monkeypatch.setattr(platform_runtime, "_is_reparse_point", lambda path: path == reparse)
    assert platform_runtime.classify_path(junction) == platform_runtime.PathKind.JUNCTION
    assert platform_runtime.classify_path(reparse) == platform_runtime.PathKind.REPARSE
    assert platform_runtime.is_link_like(junction)
    assert platform_runtime.is_link_like(reparse)


@pytest.mark.skipif(os.name != "nt", reason="native Windows junction behavior")
def test_native_windows_junction_is_classified(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    junction = tmp_path / "junction"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert platform_runtime.classify_path(junction) == platform_runtime.PathKind.JUNCTION
    assert platform_runtime.is_link_like(junction)
