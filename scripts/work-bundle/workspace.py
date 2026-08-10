from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Callable


MODES = frozenset({'single-repository', 'multi-repository'})


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_root: Path
    mode: str
    project_root: Path | None = None

    def validate(self) -> None:
        if self.mode not in MODES:
            raise ValueError('WB_WORKSPACE_MODE_INVALID')
        if self.mode == 'single-repository' and self.project_root and self.project_root.resolve() != self.workspace_root.resolve():
            raise ValueError('WB_WORKSPACE_ROOT_CONTRADICTION')


class WorkspaceTransaction:
    """Own a bounded, file-only publication transaction.

    Callers stage complete file payloads, verify external prerequisites, then
    publish with atomic replacements.  A failed publication restores original
    bytes and leaves a redacted record that is safe to carry into retry logic.
    """

    def __init__(self, workspace_root: Path, transaction_id: str | None = None) -> None:
        self.workspace_root = workspace_root.resolve()
        self.changed_paths: list[Path] = []
        self.transaction_id = transaction_id or hashlib.sha256(
            str(self.workspace_root).encode('utf-8')
        ).hexdigest()[:16]
        self.state = 'proposed'
        self._staged: dict[Path, bytes] = {}
        self._before: dict[Path, bytes | None] = {}
        self.failure_code: str | None = None

    def own(self, path: Path) -> None:
        resolved = path.expanduser().resolve(strict=False)
        if resolved != self.workspace_root and self.workspace_root not in resolved.parents:
            raise ValueError('WB_TRANSACTION_PATH_ESCAPE')
        if resolved not in self.changed_paths:
            self.changed_paths.append(resolved)

    def stage_bytes(self, path: Path, payload: bytes) -> None:
        self.own(path)
        resolved = path.expanduser().resolve(strict=False)
        self._staged[resolved] = payload
        self._before.setdefault(resolved, resolved.read_bytes() if resolved.is_file() else None)

    def stage_text(self, path: Path, payload: str) -> None:
        self.stage_bytes(path, payload.encode('utf-8'))

    def publish(self, verify: Callable[[], bool] | None = None) -> dict[str, object]:
        self.state = 'applying'
        if verify is not None and not verify():
            return self.fail('WB_TRANSACTION_VERIFICATION_FAILED')
        published: list[Path] = []
        try:
            for path, payload in self._staged.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=str(path.parent))
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
                published.append(path)
            self.state = 'published'
            return self.result()
        except OSError:
            self._restore(published)
            return self.fail('WB_TRANSACTION_PUBLISH_FAILED')

    def _restore(self, paths: list[Path]) -> None:
        for path in reversed(paths):
            before = self._before.get(path)
            if before is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(before)

    def fail(self, code: str) -> dict[str, object]:
        self.state = 'failed'
        self.failure_code = code
        return self.result()

    def rollback(self) -> dict[str, object]:
        self._restore(list(self._staged))
        self.state = 'rolled-back'
        return self.result()

    def result(self) -> dict[str, object]:
        result: dict[str, object] = {
            'id': self.transaction_id,
            'state': self.state,
            'owned_paths': [str(path) for path in sorted(self.changed_paths)],
        }
        if self.failure_code:
            result['failure_code'] = self.failure_code
        return result
