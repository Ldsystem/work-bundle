"""Versioned structural identity projections for orchestration plan artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from artifact_inputs import parse_yaml_subset


STRUCTURAL_PLAN_PROJECTION_SCHEMA = "plan-structural-projection-v2"

# V2 ignores lifecycle data only at these documented structural locations.
# ``*`` denotes one list element; names that happen to match at any other path
# remain substantive and therefore affect identity.
V2_LIFECYCLE_LOCATIONS = frozenset(
    {
        ("status",),
        ("last_updated",),
        ("updated_at",),
        ("accepted_result",),
        ("accepted_results",),
        ("accepted_result_reference",),
        ("accepted_result_references",),
        ("evidence_reference",),
        ("evidence_references",),
        ("review_id",),
        ("target_identity",),
        ("review_mode",),
        ("repair_frontier",),
        ("review_reset",),
        ("task_index", "*", "status"),
        ("acceptance_review", "verdict"),
        ("acceptance_review", "reviewed_head"),
        ("acceptance_review", "findings"),
    }
)

# This body field is lifecycle wherever its exact Markdown field syntax occurs.
# It is deliberately not scoped by a section heading: headings are presentation,
# and must never decide which surrounding requirement prose enters identity.
V2_BODY_LIFECYCLE_FIELDS = frozenset({"Closure return"})

LEGACY_APPEND_ONLY_FIELDS = frozenset(
    {
        "accepted_result",
        "accepted_results",
        "accepted_result_reference",
        "accepted_result_references",
        "evidence_reference",
        "evidence_references",
        "review_id",
        "target_identity",
        "review_mode",
        "repair_frontier",
        "review_reset",
    }
)


def _artifact_parts(path: Path, content: str | None = None) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8") if content is None else content.rstrip() + "\n"
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise SystemExit(f"stage review: missing artifact front matter: {path}")
    raw, body = text[4:].split("\n---\n", 1)
    metadata = parse_yaml_subset(raw)
    if not isinstance(metadata, dict) or not metadata.get("id"):
        raise SystemExit(f"stage review: missing artifact identity: {path}")
    return metadata, body


def _location_matches(path: tuple[str, ...]) -> bool:
    return any(
        len(location) == len(path)
        and all(expected == "*" or expected == actual for expected, actual in zip(location, path))
        for location in V2_LIFECYCLE_LOCATIONS
    )


def _structural_value_v2(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {
            key: _structural_value_v2(child, (*path, key))
            for key, child in sorted(value.items())
            if not _location_matches((*path, key))
        }
    if isinstance(value, list):
        return [_structural_value_v2(child, (*path, "*")) for child in value]
    return value


def structural_plan_artifact_v2(path: Path, *, content: str | None = None) -> dict[str, Any]:
    """Project one artifact using only the explicit V2 lifecycle locations.

    Apart from exact documented lifecycle fields, the complete Markdown body is
    structural. No heading or section pattern can exclude requirements.
    """

    metadata, body = _artifact_parts(path, content)
    lifecycle_label = re.escape(next(iter(V2_BODY_LIFECYCLE_FIELDS)))
    closure_pattern = re.compile(
        rf"^(?P<prefix>-\s+(?:\*\*{lifecycle_label}\*\*|{lifecycle_label}):[ \t]*)"
        r"(?:missing|completed|not-needed|blocked)(?P<suffix>[ \t]*)$",
        re.MULTILINE,
    )
    structural_body = closure_pattern.sub(r"\g<prefix>missing\g<suffix>", body)
    return {"metadata": _structural_value_v2(metadata), "body": structural_body}


def legacy_semantic_plan_value(value: Any, *, top_level: bool = False) -> Any:
    """Original name-based projection retained only for legacy interpretation."""

    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        created = value.get("date_created")
        for key, child in sorted(value.items()):
            if key in LEGACY_APPEND_ONLY_FIELDS:
                continue
            if top_level and key in {"status", "last_updated", "updated_at"}:
                continue
            if key == "status":
                projected[key] = "Planned"
            elif key in {"last_updated", "updated_at"} and created is not None:
                projected[key] = legacy_semantic_plan_value(created)
            elif key == "verdict":
                projected[key] = "pending"
            elif key == "reviewed_head":
                projected[key] = ""
            elif key == "findings":
                projected[key] = []
            else:
                projected[key] = legacy_semantic_plan_value(child)
        return projected
    if isinstance(value, list):
        return [legacy_semantic_plan_value(child) for child in value]
    return value


def legacy_semantic_plan_body(body: str) -> str:
    """Original heading-based closure normalization for legacy interpretation."""

    section_pattern = re.compile(
        r"^##\s+(?:2\.1\s+)?Knowledge Base Update Carry Forward\s*$"
        r"[\s\S]*?(?=^##\s|\Z)",
        re.MULTILINE,
    )
    closure_pattern = re.compile(
        r"^(?P<prefix>-\s+(?:\*\*Closure\ return\*\*|Closure\ return):[ \t]*)"
        r"(?:missing|completed|not-needed|blocked)(?P<suffix>[ \t]*)$",
        re.MULTILINE,
    )

    def normalize_closure(match: re.Match[str]) -> str:
        return closure_pattern.sub(r"\g<prefix>missing\g<suffix>", match.group(0))

    return section_pattern.sub(normalize_closure, body)


def legacy_semantic_plan_artifact(
    path: Path, *, content: str | None = None
) -> dict[str, Any]:
    metadata, body = _artifact_parts(path, content)
    return {
        "metadata": legacy_semantic_plan_value(metadata, top_level=True),
        "body": legacy_semantic_plan_body(body),
    }


def plan_artifact_projection_digest(projection: Mapping[str, Any]) -> str:
    payload = json.dumps(
        [projection["metadata"], projection["body"]],
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def semantic_plan_member_key(plan_root: Path, path: Path) -> str:
    parts = list(path.relative_to(plan_root).parts)
    if parts and parts[0] == "archived":
        parts[0] = "active"
    return Path(*parts).as_posix()
