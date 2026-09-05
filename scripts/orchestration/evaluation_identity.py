#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import os
import stat
import subprocess
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
STATUSES = frozenset({"frozen", "valid", "stale", "invalid"})
COMPONENT_FIELDS = {
    "product": "product",
    "specification": "specification",
    "tasks": "task_set_digest",
    "instruction": "instruction_digest",
    "fixture": "fixture_digest",
    "runner": "runner_digest",
    "verifier": "verifier_digest",
    "semantic_schema": "semantic_schema_digest",
    "evidence_capabilities": "evidence_capabilities_digest",
}
FREEZE_COMPONENTS = {
    "tasks": "task_set",
    "instruction": "instruction",
    "fixture": "fixture",
    "runner": "runner",
    "verifier": "verifier",
    "semantic_schema": "semantic_schema",
    "evidence_capabilities": "evidence_capabilities",
}
REQUIRED_KEYS = frozenset(
    {
        "evaluation_id", "product", "specification", "task_set_digest",
        "instruction_digest", "fixture_digest", "runner_digest",
        "verifier_digest", "semantic_schema_digest",
        "evidence_capabilities_digest", "invocation_digest",
        "raw_response_digest", "raw_trace_digest", "adjudication_digest",
        "packaging", "status", "invalidations",
    }
)
GIT_POINT_KEYS = frozenset({"repository", "revision", "tree"})
TARGET_KEYS = frozenset({"artifact_id", "revision", "sha256", "source_tree"})
INVALIDATION_KEYS = frozenset(
    {"invalidation_id", "changed_component", "old_digest", "new_digest", "affected_run_ids", "reason", "timestamp"}
)
DIGEST_FIELDS = (
    "task_set_digest", "instruction_digest", "fixture_digest", "runner_digest",
    "verifier_digest", "semantic_schema_digest", "evidence_capabilities_digest",
    "invocation_digest", "raw_response_digest", "raw_trace_digest", "adjudication_digest",
)
IMMUTABLE_TRANSITION_FIELDS = (
    "evaluation_id", "product", "specification", *DIGEST_FIELDS,
    "freeze_digest", "invocation_started_at", "completed_at",
)
GRADING_TOKENS = frozenset(
    {"adjudicate", "adjudication", "grade", "grader", "grading", "oracle", "score", "scoring", "verifier", "verify"}
)


class EvaluationIdentityError(ValueError):
    pass


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return deepcopy(value)


@dataclass(frozen=True)
class EvaluationFreezeV1:
    evaluation_id: str
    frozen_at: str
    product: Mapping[str, Any]
    specification: Mapping[str, Any]
    task_set: Mapping[str, Any]
    instruction: Mapping[str, Any]
    fixture: Mapping[str, Any]
    runner: Mapping[str, Any]
    verifier: Mapping[str, Any]
    semantic_schema: Mapping[str, Any]
    evidence_capabilities: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {field: _thaw(getattr(self, field)) for field in self.__dataclass_fields__}

    @property
    def freeze_digest(self) -> str:
        return _canonical_digest(self.to_dict())


@dataclass(frozen=True)
class EvaluationIdentityV1:
    evaluation_id: str
    product: Mapping[str, Any]
    specification: Mapping[str, Any]
    task_set_digest: str
    instruction_digest: str
    fixture_digest: str
    runner_digest: str
    verifier_digest: str
    semantic_schema_digest: str
    evidence_capabilities_digest: str
    invocation_digest: str
    raw_response_digest: str
    raw_trace_digest: str
    adjudication_digest: str
    packaging: Mapping[str, Any] | None
    status: str
    invalidations: tuple[Mapping[str, Any], ...]
    freeze_digest: str
    invocation_started_at: str
    completed_at: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            field: _thaw(getattr(self, field))
            for field in REQUIRED_KEYS
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "evaluation-completion-v1",
            "freeze_digest": self.freeze_digest,
            "invocation_started_at": self.invocation_started_at,
            "completed_at": self.completed_at,
            "evaluation": self.to_api_dict(),
        }


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvaluationIdentityError(f"{name} must be an object")
    return value


def _closed(value: Mapping[str, Any], keys: frozenset[str], name: str) -> None:
    missing = sorted(keys - value.keys())
    unknown = sorted(value.keys() - keys)
    if missing:
        raise EvaluationIdentityError(f"{name} missing required fields: {', '.join(missing)}")
    if unknown:
        raise EvaluationIdentityError(f"{name} contains unknown fields: {', '.join(unknown)}")


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationIdentityError(f"{name} must be a non-empty string")
    return value


def _identifier(value: Any, name: str) -> str:
    text = _nonempty(value, name)
    if not ID_RE.fullmatch(text):
        raise EvaluationIdentityError(f"{name} is not a valid id")
    return text


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise EvaluationIdentityError(f"{name} must be a lowercase SHA-256")
    return value


def _git_oid(value: Any, name: str) -> str:
    if not isinstance(value, str) or not GIT_OID_RE.fullmatch(value):
        raise EvaluationIdentityError(f"{name} must be a Git object id")
    return value


def _rfc3339_utc(value: Any, name: str) -> str:
    text = _nonempty(value, name)
    if not text.endswith("Z"):
        raise EvaluationIdentityError(f"{name} must be RFC3339 UTC")
    try:
        datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise EvaluationIdentityError(f"{name} must be RFC3339 UTC") from error
    return text


def _rfc3339_datetime(value: Any, name: str) -> datetime:
    text = _rfc3339_utc(value, name)
    return datetime.fromisoformat(text.removesuffix("Z") + "+00:00")


def _git_point(value: Any, name: str) -> Mapping[str, Any]:
    point = _mapping(value, name)
    _closed(point, GIT_POINT_KEYS, name)
    _nonempty(point["repository"], f"{name}.repository")
    _git_oid(point["revision"], f"{name}.revision")
    _git_oid(point["tree"], f"{name}.tree")
    return MappingProxyType(_thaw(point))


def _target_identity(value: Any) -> Mapping[str, Any]:
    target = _mapping(value, "specification")
    _closed(target, TARGET_KEYS, "specification")
    _identifier(target["artifact_id"], "specification.artifact_id")
    _nonempty(target["revision"], "specification.revision")
    _digest(target["sha256"], "specification.sha256")
    if target["source_tree"] is not None:
        _git_oid(target["source_tree"], "specification.source_tree")
    return MappingProxyType(_thaw(target))


def _invalidation(value: Any, index: int) -> Mapping[str, Any]:
    name = f"invalidations[{index}]"
    record = _mapping(value, name)
    _closed(record, INVALIDATION_KEYS, name)
    _identifier(record["invalidation_id"], f"{name}.invalidation_id")
    component = str(record["changed_component"])
    if component not in COMPONENT_FIELDS:
        raise EvaluationIdentityError(f"{name}.changed_component is invalid")
    old = _digest(record["old_digest"], f"{name}.old_digest")
    new = _digest(record["new_digest"], f"{name}.new_digest")
    if old == new:
        raise EvaluationIdentityError(f"{name} must record different old and new digests")
    affected = record["affected_run_ids"]
    if not isinstance(affected, list) or not affected:
        raise EvaluationIdentityError(f"{name}.affected_run_ids must be a non-empty list")
    for run_index, run_id in enumerate(affected):
        _identifier(run_id, f"{name}.affected_run_ids[{run_index}]")
    _nonempty(record["reason"], f"{name}.reason")
    _rfc3339_utc(record["timestamp"], f"{name}.timestamp")
    return MappingProxyType(_thaw(record))


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(_thaw(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path, name: str = "exact file") -> str:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise EvaluationIdentityError(f"{name} does not exist: {resolved}")
    return hashlib.sha256(resolved.read_bytes()).hexdigest()


def _file_identity(path: Path, name: str) -> Mapping[str, Any]:
    resolved = path.expanduser().resolve()
    return MappingProxyType({"path": str(resolved), "sha256": _file_digest(resolved, name)})


def _file_set(files: Sequence[Path], name: str) -> Mapping[str, Any]:
    if not files:
        raise EvaluationIdentityError(f"{name} requires at least one exact file")
    records = [_file_identity(Path(path), f"{name} exact file") for path in files]
    paths = [record["path"] for record in records]
    if len(paths) != len(set(paths)):
        raise EvaluationIdentityError(f"{name} exact files must be unique")
    payload = [_thaw(record) for record in records]
    return MappingProxyType({"files": tuple(records), "sha256": _canonical_digest(payload)})


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise EvaluationIdentityError(f"product root is not a readable Git repository: {detail}")
    return result.stdout.strip()


def _product_identity(root: Path) -> Mapping[str, Any]:
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise EvaluationIdentityError(f"product root does not exist: {resolved}")
    dirty = _git(resolved, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        raise EvaluationIdentityError("product identity drift: a clean product worktree is required")
    return MappingProxyType(
        {
            "repository": str(resolved),
            "revision": _git(resolved, "rev-parse", "HEAD"),
            "tree": _git(resolved, "rev-parse", "HEAD^{tree}"),
        }
    )


# Generated evidence is packaging, not product input. Other output locations
# must be declared explicitly; never guess from a filename such as "result.json".
OBSERVATION_ARTIFACT_ROOTS = (
    ".work-bundle/runtime/", ".work-bundle/orchestration/handoff/",
    ".work-bundle/orchestration/reviews/", ".work-bundle/logs/",
)


def validation_source_identity(
    root: Path, *, input_paths: Sequence[str] = (), output_paths: Sequence[str] = (),
) -> dict[str, Any]:
    """Content-address the conservative material source set, separately from receipts.

    Compute real Git blob/tree hashes without writing objects or the user's index.
    Include dirty/untracked content and declared ignored inputs. Index identity is
    retained separately because commands can inspect staged state. HEAD/packaging
    history is not a content input; callers bind it explicitly when claim-relevant.
    """
    root = root.resolve()

    def excluded(relative: str) -> bool:
        return relative.startswith(OBSERVATION_ARTIFACT_ROOTS) or any(
            relative == path or relative.startswith(path.rstrip("/") + "/")
            for path in output_paths
        )

    listed = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    paths = set(filter(None, listed.split("\0")))
    for pattern in input_paths:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise EvaluationIdentityError("validation input must be repository-relative")
        # Task write scopes may name a directory or a narrow glob.
        for candidate in root.glob(pattern):
            candidates = candidate.rglob("*") if candidate.is_dir() and not candidate.is_symlink() else [candidate]
            paths.update(p.relative_to(root).as_posix() for p in candidates if not p.is_dir() or p.is_symlink())
    index = []
    for record in _git(root, "ls-files", "--stage", "-z").split("\0"):
        if "\t" in record:
            meta, relative = record.split("\t", 1)
            if not excluded(relative):
                index.append((relative, meta))

    def object_id(kind: bytes, payload: bytes) -> bytes:
        return hashlib.sha1(kind + b" " + str(len(payload)).encode() + b"\0" + payload).digest()

    tree: dict[str, Any] = {}
    for relative in sorted(paths):
        if excluded(relative):
            continue
        if "credentials" in Path(relative).parts or Path(relative).name == ".env":
            raise EvaluationIdentityError("protected validation input requires a governed dependency identity")
        target = root / relative
        if not target.exists() and not target.is_symlink():
            continue
        if "credentials" in target.resolve().parts or target.resolve().name == ".env":
            raise EvaluationIdentityError("protected validation input requires a governed dependency identity")
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root):
            raise EvaluationIdentityError("validation source contains an unsupported link or submodule")
        mode = b"100755" if target.stat().st_mode & stat.S_IXUSR else b"100644"
        node = tree
        parts = Path(relative).parts
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = (mode, object_id(b"blob", target.read_bytes()))

    def tree_id(node: dict[str, Any]) -> bytes:
        payload = b""
        for name, child in sorted(node.items(), key=lambda pair: os.fsencode(pair[0]) + (b"/" if isinstance(pair[1], dict) else b"")):
            mode, oid = (b"40000", tree_id(child)) if isinstance(child, dict) else child
            payload += mode + b" " + os.fsencode(name) + b"\0" + oid
        return object_id(b"tree", payload)

    return {"tree": tree_id(tree).hex(), "index_digest": _canonical_digest(index)}


def _api_product(product: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: product[key] for key in GIT_POINT_KEYS})


def _api_specification(specification: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: specification[key] for key in TARGET_KEYS})


def _module_candidates(current: Path, product_root: Path, module: str, level: int) -> list[Path]:
    base = current.parent
    for _ in range(max(level - 1, 0)):
        base = base.parent
    relative = Path(*module.split(".")) if module else Path()
    candidates = [base / relative.with_suffix(".py"), base / relative / "__init__.py"]
    if level == 0:
        candidates.extend([product_root / relative.with_suffix(".py"), product_root / relative / "__init__.py"])
    return [candidate.resolve() for candidate in candidates]


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _names(node: ast.AST) -> set[str]:
    return {item.id.lower() for item in ast.walk(node) if isinstance(item, ast.Name)}


def _validate_runner_graph(product_root: Path, runner_file: Path, runner_entrypoint: str, verifier_file: Path, verifier_entrypoint: str) -> None:
    runner = runner_file.expanduser().resolve()
    verifier = verifier_file.expanduser().resolve()
    if runner == verifier:
        raise EvaluationIdentityError("runner and verifier must use a separate entrypoint file")
    visited: set[Path] = set()
    pending = [runner]
    found_runner = False
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        try:
            tree = ast.parse(current.read_text(encoding="utf-8"), filename=str(current))
        except (OSError, SyntaxError, UnicodeError) as error:
            raise EvaluationIdentityError(f"runner dependency is not valid Python: {current}: {error}") from error
        if current == runner:
            found_runner = any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == runner_entrypoint for node in tree.body)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call = _call_name(node.func).lower()
                tokens = set(re.findall(r"[a-z]+", call))
                if verifier_entrypoint.lower() in tokens or tokens & GRADING_TOKENS:
                    raise EvaluationIdentityError(f"runner dependency graph calls verifier or grading semantics: {call}")
                if call in {"__import__", "importlib.import_module"} and node.args and isinstance(node.args[0], ast.Constant):
                    imported = str(node.args[0].value).lower()
                    imported_tokens = set(re.findall(r"[a-z]+", imported))
                    if imported_tokens & GRADING_TOKENS or Path(imported.replace(".", "/")).name == verifier.stem.lower():
                        raise EvaluationIdentityError(f"runner dynamically imports verifier or grading semantics: {imported}")
            if isinstance(node, ast.Compare):
                names = _names(node)
                expected = any("expected" in name or "oracle" in name for name in names)
                actual = any("actual" in name or "result" in name for name in names)
                if expected and actual:
                    raise EvaluationIdentityError("runner dependency graph contains grading comparison semantics")
            modules: list[tuple[str, int]] = []
            if isinstance(node, ast.Import):
                modules = [(alias.name, 0) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                modules = [(base, node.level)]
                modules.extend(
                    (f"{base}.{alias.name}" if base else alias.name, node.level)
                    for alias in node.names
                    if alias.name != "*"
                )
            for module, level in modules:
                module_tokens = set(re.findall(r"[a-z]+", module.lower()))
                if module_tokens & GRADING_TOKENS or Path(module.replace(".", "/")).name == verifier.stem.lower():
                    raise EvaluationIdentityError(f"runner imports verifier or grading semantics: {module}")
                for candidate in _module_candidates(current, product_root, module, level):
                    if candidate == verifier:
                        raise EvaluationIdentityError("runner dependency graph imports verifier")
                    try:
                        candidate.relative_to(product_root)
                    except ValueError:
                        continue
                    if candidate.is_file():
                        pending.append(candidate)
                        break
    if not found_runner:
        raise EvaluationIdentityError(f"runner entrypoint not found: {runner_entrypoint}")
    try:
        verifier_tree = ast.parse(verifier.read_text(encoding="utf-8"), filename=str(verifier))
    except (OSError, SyntaxError, UnicodeError) as error:
        raise EvaluationIdentityError(f"verifier is not valid Python: {verifier}: {error}") from error
    if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == verifier_entrypoint for node in verifier_tree.body):
        raise EvaluationIdentityError(f"verifier separate entrypoint not found: {verifier_entrypoint}")


def freeze_evaluation_identity(
    *, evaluation_id: str, product_root: Path, specification_id: str,
    specification_revision: str, specification_file: Path,
    task_files: Sequence[Path], instruction_files: Sequence[Path], fixture_files: Sequence[Path],
    runner_file: Path, runner_entrypoint: str, verifier_file: Path, verifier_entrypoint: str,
    semantic_schema_files: Sequence[Path], evidence_capability_files: Sequence[Path], frozen_at: str,
) -> EvaluationFreezeV1:
    evaluation_id = _identifier(evaluation_id, "evaluation_id")
    frozen_at = _rfc3339_utc(frozen_at, "frozen_at")
    root = product_root.expanduser().resolve()
    product = _product_identity(root)
    specification_source = _file_identity(specification_file, "specification exact file")
    specification = MappingProxyType(
        {
            "artifact_id": _identifier(specification_id, "specification_id"),
            "revision": _nonempty(specification_revision, "specification_revision"),
            "sha256": specification_source["sha256"],
            "source_tree": None,
            "path": specification_source["path"],
        }
    )
    runner_source = _file_identity(runner_file, "runner exact file")
    verifier_source = _file_identity(verifier_file, "verifier exact file")
    runner = MappingProxyType({**_thaw(runner_source), "entrypoint": _nonempty(runner_entrypoint, "runner_entrypoint")})
    verifier = MappingProxyType({**_thaw(verifier_source), "entrypoint": _nonempty(verifier_entrypoint, "verifier_entrypoint")})
    _validate_runner_graph(root, Path(runner["path"]), runner["entrypoint"], Path(verifier["path"]), verifier["entrypoint"])
    return EvaluationFreezeV1(
        evaluation_id=evaluation_id, frozen_at=frozen_at, product=product, specification=specification,
        task_set=_file_set(task_files, "task_set"), instruction=_file_set(instruction_files, "instruction"),
        fixture=_file_set(fixture_files, "fixture"), runner=runner, verifier=verifier,
        semantic_schema=_file_set(semantic_schema_files, "semantic_schema"),
        evidence_capabilities=_file_set(evidence_capability_files, "evidence_capabilities"),
    )


def validate_evaluation_freeze(freeze: EvaluationFreezeV1, *, verify_sources: bool = True) -> EvaluationFreezeV1:
    if not isinstance(freeze, EvaluationFreezeV1):
        raise EvaluationIdentityError("prior freeze record is required")
    _identifier(freeze.evaluation_id, "evaluation_id")
    _rfc3339_utc(freeze.frozen_at, "frozen_at")
    if verify_sources:
        current_product = _product_identity(Path(freeze.product["repository"]))
        if _thaw(current_product) != _thaw(freeze.product):
            raise EvaluationIdentityError("product identity drift after pre-invocation freeze")
        if _file_digest(Path(freeze.specification["path"]), "specification exact file") != freeze.specification["sha256"]:
            raise EvaluationIdentityError("specification identity drift after pre-invocation freeze")
        for name in ("task_set", "instruction", "fixture", "semantic_schema", "evidence_capabilities"):
            identity = getattr(freeze, name)
            current = _file_set([Path(item["path"]) for item in identity["files"]], name)
            if _thaw(current) != _thaw(identity):
                raise EvaluationIdentityError(f"{name} identity drift after pre-invocation freeze")
        for name in ("runner", "verifier"):
            identity = getattr(freeze, name)
            if _file_digest(Path(identity["path"]), f"{name} exact file") != identity["sha256"]:
                raise EvaluationIdentityError(f"{name} identity drift after pre-invocation freeze")
        _validate_runner_graph(
            Path(freeze.product["repository"]), Path(freeze.runner["path"]), freeze.runner["entrypoint"],
            Path(freeze.verifier["path"]), freeze.verifier["entrypoint"],
        )
    return freeze


def _parse_identity(value: Mapping[str, Any], *, provenance: Mapping[str, Any] | None = None) -> EvaluationIdentityV1:
    record = _mapping(value, "evaluation_identity_v1")
    _closed(record, REQUIRED_KEYS, "evaluation_identity_v1")
    evaluation_id = _identifier(record["evaluation_id"], "evaluation_id")
    product = _git_point(record["product"], "product")
    specification = _target_identity(record["specification"])
    digests = {field: _digest(record[field], field) for field in DIGEST_FIELDS}
    packaging = None if record["packaging"] is None else _git_point(record["packaging"], "packaging")
    if record["status"] not in STATUSES:
        raise EvaluationIdentityError(f"status must be one of: {', '.join(sorted(STATUSES))}")
    raw_invalidations = record["invalidations"]
    if not isinstance(raw_invalidations, list):
        raise EvaluationIdentityError("invalidations must be a list")
    invalidations = tuple(_invalidation(item, index) for index, item in enumerate(raw_invalidations))
    ids = [str(item["invalidation_id"]) for item in invalidations]
    if len(ids) != len(set(ids)):
        raise EvaluationIdentityError("invalidation IDs must be unique and append-only")
    if provenance is None:
        raise EvaluationIdentityError("completed evaluation requires prior freeze provenance")
    freeze_digest = _digest(provenance.get("freeze_digest"), "freeze_digest")
    started = _rfc3339_utc(provenance.get("invocation_started_at"), "invocation_started_at")
    completed = _rfc3339_utc(provenance.get("completed_at"), "completed_at")
    return EvaluationIdentityV1(
        evaluation_id=evaluation_id, product=product, specification=specification, packaging=packaging,
        status=str(record["status"]), invalidations=invalidations, freeze_digest=freeze_digest,
        invocation_started_at=started, completed_at=completed, **digests,
    )


def validate_evaluation_identity(value: Mapping[str, Any] | EvaluationIdentityV1) -> EvaluationIdentityV1:
    if isinstance(value, EvaluationIdentityV1):
        _parse_identity(value.to_api_dict(), provenance=value.to_dict())
        return value
    document = _mapping(value, "evaluation completion")
    if document.get("schema") == "evaluation-completion-v1":
        return _parse_identity(_mapping(document.get("evaluation"), "evaluation"), provenance=document)
    raise EvaluationIdentityError("completed evaluation requires prior freeze provenance")


def complete_evaluation_identity(
    freeze: EvaluationFreezeV1 | None, *, invocation_file: Path, raw_response_file: Path,
    raw_trace_file: Path, adjudication_file: Path, invocation_started_at: str,
    completed_at: str, packaging: Mapping[str, Any] | None = None,
) -> EvaluationIdentityV1:
    if freeze is None:
        raise EvaluationIdentityError("prior freeze record is required before invocation completion")
    validate_evaluation_freeze(freeze, verify_sources=True)
    started = _rfc3339_utc(invocation_started_at, "invocation_started_at")
    completed = _rfc3339_utc(completed_at, "completed_at")
    frozen_instant = _rfc3339_datetime(freeze.frozen_at, "frozen_at")
    started_instant = _rfc3339_datetime(started, "invocation_started_at")
    completed_instant = _rfc3339_datetime(completed, "completed_at")
    if not (frozen_instant <= started_instant <= completed_instant):
        raise EvaluationIdentityError("freeze, invocation, and completion timestamps are out of order")
    result = EvaluationIdentityV1(
        evaluation_id=freeze.evaluation_id, product=_api_product(freeze.product),
        specification=_api_specification(freeze.specification), task_set_digest=freeze.task_set["sha256"],
        instruction_digest=freeze.instruction["sha256"], fixture_digest=freeze.fixture["sha256"],
        runner_digest=freeze.runner["sha256"], verifier_digest=freeze.verifier["sha256"],
        semantic_schema_digest=freeze.semantic_schema["sha256"],
        evidence_capabilities_digest=freeze.evidence_capabilities["sha256"],
        invocation_digest=_file_digest(invocation_file, "invocation exact file"),
        raw_response_digest=_file_digest(raw_response_file, "raw response exact file"),
        raw_trace_digest=_file_digest(raw_trace_file, "raw trace exact file"),
        adjudication_digest=_file_digest(adjudication_file, "adjudication exact file"),
        packaging=None if packaging is None else _git_point(packaging, "packaging"), status="valid", invalidations=(),
        freeze_digest=freeze.freeze_digest, invocation_started_at=started, completed_at=completed,
    )
    return validate_evaluation_identity(result)


def _component_digest(identity: EvaluationIdentityV1, component: str) -> str:
    if component in {"product", "specification"}:
        return _canonical_digest(getattr(identity, component))
    return getattr(identity, COMPONENT_FIELDS[component])


def _freeze_component_digest(freeze: EvaluationFreezeV1, component: str) -> str:
    if component == "product":
        return _canonical_digest(_api_product(freeze.product))
    if component == "specification":
        return _canonical_digest(_api_specification(freeze.specification))
    return getattr(freeze, FREEZE_COMPONENTS[component])["sha256"]


def validate_evaluation_transition(
    previous: EvaluationIdentityV1, current: EvaluationIdentityV1, *, evidence_corruption: bool = False,
) -> EvaluationIdentityV1:
    previous = validate_evaluation_identity(previous)
    current = validate_evaluation_identity(current)
    prefix = current.invalidations[: len(previous.invalidations)]
    if _thaw(prefix) != _thaw(previous.invalidations):
        raise EvaluationIdentityError("invalidation history must preserve the previous append-only prefix")
    for field in IMMUTABLE_TRANSITION_FIELDS:
        if _thaw(getattr(current, field)) != _thaw(getattr(previous, field)):
            raise EvaluationIdentityError(f"{field} is immutable across evaluation transitions")
    appended = current.invalidations[len(previous.invalidations):]
    if appended:
        if current.status != "stale":
            raise EvaluationIdentityError("component drift must transition the evaluation to stale")
        if _thaw(current.packaging) != _thaw(previous.packaging):
            raise EvaluationIdentityError("packaging cannot change in a component invalidation transition")
    else:
        if current.status == "invalid" and not evidence_corruption:
            raise EvaluationIdentityError("invalid status is reserved for evidence corruption")
        if current.status != previous.status and not (evidence_corruption and current.status == "invalid"):
            raise EvaluationIdentityError("status cannot change without component drift or evidence corruption")
    return current


def invalidate_changed_components(
    identity: EvaluationIdentityV1, current_freeze: EvaluationFreezeV1, *, affected_run_ids: Sequence[str],
    reason: str, timestamp: str, invalidation_id: str, packaging: Mapping[str, Any] | None = None,
) -> EvaluationIdentityV1:
    previous = validate_evaluation_identity(identity)
    current_freeze = validate_evaluation_freeze(current_freeze, verify_sources=True)
    if previous.evaluation_id != current_freeze.evaluation_id:
        raise EvaluationIdentityError("current freeze must describe the same evaluation_id")
    if not affected_run_ids:
        raise EvaluationIdentityError("affected_run_ids must be non-empty")
    runs = [_identifier(run_id, "affected_run_id") for run_id in affected_run_ids]
    reason = _nonempty(reason, "reason")
    timestamp = _rfc3339_utc(timestamp, "timestamp")
    invalidation_id = _identifier(invalidation_id, "invalidation_id")
    changed = []
    for component in COMPONENT_FIELDS:
        old_digest = _component_digest(previous, component)
        new_digest = _freeze_component_digest(current_freeze, component)
        if old_digest != new_digest:
            changed.append((component, old_digest, new_digest))
    additions = []
    existing = {_thaw(item)["invalidation_id"] for item in previous.invalidations}
    for component, old_digest, new_digest in changed:
        record_id = invalidation_id if len(changed) == 1 else f"{invalidation_id}-{component}"
        if record_id in existing:
            raise EvaluationIdentityError(f"invalidation_id already exists: {record_id}")
        additions.append(
            MappingProxyType(
                {
                    "invalidation_id": record_id, "changed_component": component,
                    "old_digest": old_digest, "new_digest": new_digest,
                    "affected_run_ids": runs, "reason": reason, "timestamp": timestamp,
                }
            )
        )
    current = replace(
        previous,
        packaging=previous.packaging if packaging is None else _git_point(packaging, "packaging"),
        status="stale" if additions else previous.status,
        invalidations=(*previous.invalidations, *additions),
    )
    return validate_evaluation_transition(previous, current)


def verify_raw_evidence_immutable(original: EvaluationIdentityV1, candidate: EvaluationIdentityV1) -> None:
    validate_evaluation_transition(original, candidate)


def _read_document(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as error:
            raise EvaluationIdentityError("YAML input requires PyYAML") from error
        value = yaml.safe_load(text)
    return _mapping(value, str(path))


def _freeze_from_dict(value: Mapping[str, Any]) -> EvaluationFreezeV1:
    expected = frozenset(EvaluationFreezeV1.__dataclass_fields__)
    _closed(value, expected, "evaluation freeze")
    result = EvaluationFreezeV1(**{field: value[field] for field in expected})
    return validate_evaluation_freeze(result, verify_sources=True)


def _print_failure(error: Exception) -> int:
    print(json.dumps({"status": "blocked", "failure_code": "WB_EVALUATION_IDENTITY_INVALID", "detail": str(error)}, sort_keys=True))
    return 1


def cmd_evaluation_identity_freeze(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py evaluation-identity-freeze")
    parser.add_argument("--evaluation-id", required=True)
    parser.add_argument("--product-root", type=Path, required=True)
    parser.add_argument("--specification-id", required=True)
    parser.add_argument("--specification-revision", required=True)
    parser.add_argument("--specification-file", type=Path, required=True)
    parser.add_argument("--task-file", type=Path, action="append", required=True)
    parser.add_argument("--instruction-file", type=Path, action="append", required=True)
    parser.add_argument("--fixture-file", type=Path, action="append", required=True)
    parser.add_argument("--runner-file", type=Path, required=True)
    parser.add_argument("--runner-entrypoint", required=True)
    parser.add_argument("--verifier-file", type=Path, required=True)
    parser.add_argument("--verifier-entrypoint", required=True)
    parser.add_argument("--semantic-schema-file", type=Path, action="append", required=True)
    parser.add_argument("--evidence-capability-file", type=Path, action="append", required=True)
    parser.add_argument("--frozen-at", required=True)
    parsed = parser.parse_args(argv)
    try:
        frozen = freeze_evaluation_identity(
            evaluation_id=parsed.evaluation_id, product_root=parsed.product_root,
            specification_id=parsed.specification_id, specification_revision=parsed.specification_revision,
            specification_file=parsed.specification_file, task_files=parsed.task_file,
            instruction_files=parsed.instruction_file, fixture_files=parsed.fixture_file,
            runner_file=parsed.runner_file, runner_entrypoint=parsed.runner_entrypoint,
            verifier_file=parsed.verifier_file, verifier_entrypoint=parsed.verifier_entrypoint,
            semantic_schema_files=parsed.semantic_schema_file,
            evidence_capability_files=parsed.evidence_capability_file, frozen_at=parsed.frozen_at,
        )
    except (OSError, EvaluationIdentityError) as error:
        return _print_failure(error)
    print(json.dumps(frozen.to_dict(), sort_keys=True))
    return 0


def cmd_evaluation_identity_complete(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py evaluation-identity-complete")
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--invocation-file", type=Path, required=True)
    parser.add_argument("--raw-response-file", type=Path, required=True)
    parser.add_argument("--raw-trace-file", type=Path, required=True)
    parser.add_argument("--adjudication-file", type=Path, required=True)
    parser.add_argument("--invocation-started-at", required=True)
    parser.add_argument("--completed-at", required=True)
    parsed = parser.parse_args(argv)
    try:
        frozen = _freeze_from_dict(_read_document(parsed.freeze))
        completed = complete_evaluation_identity(
            frozen, invocation_file=parsed.invocation_file, raw_response_file=parsed.raw_response_file,
            raw_trace_file=parsed.raw_trace_file, adjudication_file=parsed.adjudication_file,
            invocation_started_at=parsed.invocation_started_at, completed_at=parsed.completed_at,
        )
    except (OSError, EvaluationIdentityError) as error:
        return _print_failure(error)
    print(json.dumps(completed.to_dict(), sort_keys=True))
    return 0


def cmd_evaluation_identity_transition(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py evaluation-identity-transition")
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--current-freeze", type=Path, required=True)
    parser.add_argument("--affected-run-id", action="append", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--timestamp", required=True)
    parser.add_argument("--invalidation-id", required=True)
    parsed = parser.parse_args(argv)
    try:
        previous = validate_evaluation_identity(_read_document(parsed.previous))
        current_freeze = _freeze_from_dict(_read_document(parsed.current_freeze))
        current = invalidate_changed_components(
            previous, current_freeze, affected_run_ids=parsed.affected_run_id, reason=parsed.reason,
            timestamp=parsed.timestamp, invalidation_id=parsed.invalidation_id,
        )
    except (OSError, EvaluationIdentityError) as error:
        return _print_failure(error)
    print(json.dumps(current.to_dict(), sort_keys=True))
    return 0


def cmd_evaluation_identity(command: str, argv: list[str]) -> int:
    commands = {
        "evaluation-identity-freeze": cmd_evaluation_identity_freeze,
        "evaluation-identity-complete": cmd_evaluation_identity_complete,
        "evaluation-identity-transition": cmd_evaluation_identity_transition,
    }
    return commands[command](argv)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluation_identity.py")
    parser.add_argument("command", choices=("freeze", "complete", "transition"))
    parsed, remaining = parser.parse_known_args(argv)
    return cmd_evaluation_identity(f"evaluation-identity-{parsed.command}", remaining)


if __name__ == "__main__":
    raise SystemExit(main())
