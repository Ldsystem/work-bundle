"""Cross-platform filesystem mechanics shared by WorkBundle runtimes.

This module owns only operating-system adaptation.  Callers retain policy,
path authority, payload validation, and semantic decisions.
"""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
import errno
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import BinaryIO, Iterator, TextIO


_IS_WINDOWS = os.name == "nt"

if _IS_WINDOWS:  # pragma: no cover - imported by native Windows CI
    import msvcrt as _MSVCRT
else:
    _MSVCRT = None
    import fcntl as _FCNTL


class PathKind(str, Enum):
    ORDINARY = "ordinary"
    MISSING = "missing"
    SYMLINK = "symlink"
    JUNCTION = "junction"
    REPARSE = "reparse"


def _is_junction(path: Path) -> bool:
    predicate = getattr(path, "is_junction", None)
    return bool(predicate()) if callable(predicate) else False


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def classify_path(path: str | os.PathLike[str]) -> PathKind:
    """Classify an unresolved path without following link-like objects."""

    candidate = Path(path)
    if candidate.is_symlink():
        return PathKind.SYMLINK
    if _is_junction(candidate):
        return PathKind.JUNCTION
    if _is_reparse_point(candidate):
        return PathKind.REPARSE
    if not candidate.exists():
        return PathKind.MISSING
    return PathKind.ORDINARY


def is_link_like(path: str | os.PathLike[str]) -> bool:
    return classify_path(path) in {PathKind.SYMLINK, PathKind.JUNCTION, PathKind.REPARSE}


def contains_link_like_component(path: Path, *, anchor: Path) -> bool:
    """Report link-like components between an existing authority anchor and path."""

    if ".." in path.parts or ".." in anchor.parts:
        return True
    lexical_anchor = Path(os.path.abspath(anchor))
    lexical_path = Path(os.path.abspath(path))
    try:
        relative = lexical_path.relative_to(lexical_anchor)
    except ValueError:
        return True
    current = lexical_anchor
    if is_link_like(current):
        return True
    for component in relative.parts:
        current /= component
        if is_link_like(current):
            return True
    return False


def _windows_lock_unavailable(error: OSError) -> bool:
    winerror = getattr(error, "winerror", None)
    if winerror is not None:
        return winerror == 33
    return error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}


def _lock_windows(descriptor: int) -> None:
    assert _MSVCRT is not None
    while True:
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            _MSVCRT.locking(descriptor, _MSVCRT.LK_NBLCK, 1)
            return
        except OSError as error:
            if not _windows_lock_unavailable(error):
                raise
            time.sleep(0.05)


@contextmanager
def blocking_file_lock(
    stream: BinaryIO | TextIO, *, shared: bool = False
) -> Iterator[None]:
    """Hold a blocking file lock; Windows conservatively serializes all access."""

    descriptor = stream.fileno()
    if _IS_WINDOWS:
        original_offset = os.lseek(descriptor, 0, os.SEEK_CUR)
        _lock_windows(descriptor)
        try:
            os.lseek(descriptor, original_offset, os.SEEK_SET)
            yield
        finally:
            current_offset: int | None = None
            try:
                current_offset = os.lseek(descriptor, 0, os.SEEK_CUR)
            finally:
                try:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                finally:
                    assert _MSVCRT is not None
                    _MSVCRT.locking(descriptor, _MSVCRT.LK_UNLCK, 1)
                    if current_offset is not None:
                        os.lseek(descriptor, current_offset, os.SEEK_SET)
        return

    operation = _FCNTL.LOCK_SH if shared else _FCNTL.LOCK_EX
    _FCNTL.flock(descriptor, operation)
    try:
        yield
    finally:
        _FCNTL.flock(descriptor, _FCNTL.LOCK_UN)


def _unsupported_capability(error: OSError) -> bool:
    return error.errno in {
        errno.EINVAL,
        errno.ENOSYS,
        errno.ENOTSUP,
        errno.EOPNOTSUPP,
    }


def _harden_mode(descriptor: int, mode: int | None) -> None:
    if mode is None:
        return
    harden = getattr(os, "fchmod", None)
    if not callable(harden):
        return
    try:
        harden(descriptor, mode)
    except (NotImplementedError, AttributeError):
        return
    except OSError as error:
        if not _unsupported_capability(error):
            raise


def _sync_parent_directory(parent: Path) -> None:
    if _IS_WINDOWS or not hasattr(os, "O_DIRECTORY"):
        return
    try:
        descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as error:
        if _unsupported_capability(error):
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if not _unsupported_capability(error):
                raise
    finally:
        os.close(descriptor)


def atomic_replace_bytes(path: Path, content: bytes, *, mode: int | None = None) -> None:
    """Atomically replace one file and use only host-supported durability features."""

    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        _harden_mode(descriptor, mode)
        stream = os.fdopen(descriptor, "wb")
        descriptor = -1
        with stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        _sync_parent_directory(target.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
