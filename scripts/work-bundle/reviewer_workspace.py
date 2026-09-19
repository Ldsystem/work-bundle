#!/usr/bin/env python3
"""Structural admission for exact Stage 5 implementation-review candidates.

This module owns no reviewer process, receipt, publication, round, or lifecycle
state. It checks only Git/source identity and reviewer independence.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping


class ReviewerWorkspaceError(ValueError):
    pass


def _git(root: Path, *args: str, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True,
        text=not binary, check=False,
    )
    if completed.returncode:
        detail = completed.stderr if isinstance(completed.stderr, str) else completed.stderr.decode("utf-8", "replace")
        raise ReviewerWorkspaceError(f"WB_REVIEW_GIT_IDENTITY_INVALID: {detail.strip()}")
    return completed.stdout


def _commit(root: Path, value: object) -> str:
    raw = str(value or "")
    if not re.fullmatch(r"[0-9a-f]{40}", raw):
        raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
    resolved = str(_git(root, "rev-parse", f"{raw}^{{commit}}")).strip()
    if resolved != raw:
        raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
    return resolved


def _manifest_bytes(manifest: list[dict[str, str]]) -> bytes:
    return "".join(
        (
            f"present {item['sha256']}  {item['path']}\n"
            if item["state"] == "present"
            else f"deleted -  {item['path']}\n"
        )
        for item in manifest
    ).encode("utf-8")


def validate_current_candidate_and_independence(
    source_root: Path,
    target: object,
    *,
    reviewer_agent_id: str,
    implementor_agent_id: str,
) -> dict[str, Any]:
    """Recompute the declared candidate and require concrete distinct identities."""

    root = source_root.expanduser().resolve()
    _git(root, "rev-parse", "--git-dir")
    if not isinstance(target, Mapping) or set(target) != {"kind", "sha256", "base_commit", "manifest"}:
        raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
    kind = target.get("kind")
    if kind not in {"commit", "worktree"}:
        raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
    base = _commit(root, target.get("base_commit"))
    raw_manifest = target.get("manifest")
    if not isinstance(raw_manifest, list):
        raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
    manifest: list[dict[str, str]] = []
    for raw in raw_manifest:
        if not isinstance(raw, Mapping):
            raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
        raw_state = raw.get("state")
        if not isinstance(raw_state, str) or raw_state not in {"present", "deleted"}:
            raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
        state = raw_state
        expected_fields = {"path", "state", "sha256"} if state == "present" else {"path", "state"}
        if set(raw) != expected_fields:
            raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
        relative = Path(str(raw.get("path") or ""))
        if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
        name = relative.as_posix()
        if kind == "commit":
            if state != "present":
                raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
            content = _git(root, "show", f"{base}:{name}", binary=True)
            assert isinstance(content, bytes)
        else:
            worktree_path = root / relative
            path = worktree_path.resolve(strict=False)
            if root not in path.parents or worktree_path.is_symlink():
                raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
            if worktree_path.is_file():
                if state != "present":
                    raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
                content = worktree_path.read_bytes()
            elif worktree_path.exists():
                raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
            else:
                if state != "deleted":
                    raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
                base_type = subprocess.run(
                    ["git", "-C", str(root), "cat-file", "-t", f"{base}:{name}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if base_type.returncode or base_type.stdout.strip() != "blob":
                    raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
                content = None
        if state == "present":
            assert content is not None
            digest = hashlib.sha256(content).hexdigest()
            if raw.get("sha256") != digest:
                raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_DIGEST_MISMATCH")
            manifest.append({"path": name, "state": state, "sha256": digest})
        else:
            manifest.append({"path": name, "state": state})
    if [item["path"] for item in manifest] != sorted({item["path"] for item in manifest}):
        raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_INVALID")
    aggregate = hashlib.sha256(_manifest_bytes(manifest)).hexdigest()
    if target.get("sha256") != aggregate:
        raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_TARGET_DIGEST_MISMATCH")
    if not reviewer_agent_id.strip() or not implementor_agent_id.strip():
        raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_REVIEWER_INVALID")
    if reviewer_agent_id == implementor_agent_id:
        raise ReviewerWorkspaceError("WB_REVIEW_CURRENT_REVIEWER_NOT_INDEPENDENT")
    return {
        "target": {"kind": kind, "sha256": aggregate, "base_commit": base, "manifest": manifest},
        "reviewer": {"agent_id": reviewer_agent_id},
        "implementor_agent_id": implementor_agent_id,
    }


def main() -> int:
    raise SystemExit("no public reviewer-process command; use orch.py write-implementation-review")


if __name__ == "__main__":
    raise SystemExit(main())
