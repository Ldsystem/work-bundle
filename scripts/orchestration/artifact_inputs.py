"""Core-independent orchestration artifact parsing and bounded input resolution."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from artifact_store import (
    canonical_artifact_path,
    family_policy,
    load_catalog,
    read_artifact,
    read_markdown_artifact,
    read_yaml_mapping,
)

SPEC_CATALOG = Path(__file__).resolve().parents[2] / "references/assets/orchestration/contract/artifact-family-catalog-v3.yaml"

def _read_structured(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("---\n"):
        return read_markdown_artifact(path)
    return read_yaml_mapping(path), ""


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "" or value == {}:
        return []
    return value if isinstance(value, list) else [value]


def _input_path(raw: str | Path, root: Path, allowed: Path, label: str) -> Path:
    path = Path(raw).expanduser()
    path = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not path.is_relative_to(allowed.resolve()):
        raise SystemExit(f"{label} path escapes its allowed root: {path}")
    relative = path.relative_to(root.resolve()).as_posix()
    if relative.startswith(".work-bundle/knowledge/") or relative.startswith("credentials/"):
        raise SystemExit(f"{label} path uses a forbidden protected source: {relative}")
    if not path.is_file():
        raise SystemExit(f"{label} file not found: {path}")
    return path


def _resolve_spec_paths(root: Path, task_data: dict[str, Any], plan_data: dict[str, Any]) -> list[Path]:
    if "source_spec" in task_data or "source_spec" in plan_data:
        raise SystemExit("Legacy source_spec aliases are unsupported; use source_spec_id")
    references = _as_list(task_data.get("source_spec_id")) or _as_list(plan_data.get("source_spec_id"))
    if not references:
        raise SystemExit("Task/root plan does not declare source_spec_id")
    policy = family_policy(load_catalog(SPEC_CATALOG), "specification")
    anchors = {"workspace_root": root}
    result: list[Path] = []
    for reference in references:
        raw = str(reference)
        if "/" in raw or raw.endswith(".md"):
            raise SystemExit("Source specification paths are unsupported; use source_spec_id")
        matches = [
            (state, canonical_artifact_path(policy, anchors, identity=raw, state=state))
            for state in ("active", "archived")
        ]
        matches = [(state, path) for state, path in matches if path.is_file()]
        if len(matches) != 1:
            raise SystemExit(f"Source specification not found at canonical location for {raw}")
        state, path = matches[0]
        read_artifact(SPEC_CATALOG, "specification", anchors, identity=raw, state=state)
        result.append(path)
    return result
