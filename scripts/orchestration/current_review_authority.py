"""Direct immutable authority bindings for already-published current reviews."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


AUTHORITY_SCHEMA = "stage-review-v2"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_BINDING_KEYS = frozenset(
    {
        "review_id",
        "record_sha256",
        "stage",
        "review_target_kind",
        "review_mode",
        "verdict",
        "target_identity",
    }
)


def authority_path(root: Path, review_id: str) -> Path:
    if not _ID_RE.fullmatch(review_id):
        raise ValueError("current review authority review_id is invalid")
    store = root.expanduser().resolve() / ".work-bundle/orchestration/review-authority"
    path = (store / f"{review_id}.json").resolve(strict=False)
    if not path.is_relative_to(store.resolve()):
        raise ValueError("current review authority path escapes authority store")
    return path


def _canonical_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _binding(record: Mapping[str, Any], record_sha256: str) -> dict[str, Any]:
    target = record.get("target_identity")
    if not isinstance(target, Mapping):
        raise ValueError("current review authority target identity is invalid")
    return {
        "review_id": str(record.get("review_id") or ""),
        "record_sha256": record_sha256,
        "stage": str(record.get("stage") or "plan"),
        "review_target_kind": str(record.get("review_target_kind") or "stage"),
        "review_mode": str(record.get("review_mode") or "initial"),
        "verdict": str(record.get("verdict") or ""),
        "target_identity": dict(target),
    }


def write_authority(root: Path, record: Mapping[str, Any], record_sha256: str) -> Path:
    """Persist one idempotent digest-bound current authority after publication checks."""

    binding = _binding(record, record_sha256)
    document = {
        "schema": AUTHORITY_SCHEMA,
        "current_authority": binding,
        "authority_sha256": _canonical_digest(binding),
    }
    content = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    path = authority_path(root, binding["review_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_mode & 0o222
            or path.read_bytes() != content
        ):
            raise ValueError("current review authority identity collision")
    else:
        with path.open("xb") as stream:
            stream.write(content)
        path.chmod(0o444)
    return path


def load_authority(
    root: Path, record: Mapping[str, Any], record_sha256: str
) -> dict[str, Any] | None:
    """Load a v2 binding without consulting receipts or predecessor records."""

    path = authority_path(root, str(record.get("review_id") or ""))
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise ValueError("current review authority is missing or mutable")
    try:
        document = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("current review authority is unreadable") from error
    if not isinstance(document, dict) or set(document) != {
        "schema", "current_authority", "authority_sha256"
    } or document.get("schema") != AUTHORITY_SCHEMA:
        raise ValueError("current review authority shape is invalid")
    binding = document.get("current_authority")
    if not isinstance(binding, dict) or set(binding) != _BINDING_KEYS:
        raise ValueError("current review authority binding shape is invalid")
    if document.get("authority_sha256") != _canonical_digest(binding):
        raise ValueError("current review authority digest mismatch")
    if binding != _binding(record, record_sha256):
        raise ValueError("current review authority does not bind the stored record")
    return binding
