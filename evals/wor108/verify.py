#!/usr/bin/env python3
"""Verify the deterministic WOR-108 closure and migration-impact package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
EXPECTED_IDS = tuple(
    [f"RF-{number:02d}" for number in range(1, 9)]
    + [f"SG-{number:02d}" for number in range(1, 9)]
    + [f"CTX-{number:02d}" for number in range(1, 7)]
)
EXPECTED_AREAS = {
    "RF": "repair_frontier",
    "SG": "subagent_ownership",
    "CTX": "context_projection",
}
FIXTURE_KEYS = {"fixture_id", "area", "title", "oracle", "pytest_nodes", "expected"}
NODE = re.compile(r"^(tests/test_wor108_[a-z_]+\.py)::(test_[a-z0-9_]+)$")
MIGRATION_KEYS = {
    "contract", "issue", "evaluation_id", "accepted_legacy_baseline",
    "changed_surfaces", "evaluation_identities", "handoff_constraints",
}
SURFACE_KEYS = {"public_contracts", "instructions", "operations", "fixtures_and_evaluations"}


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError(f"object required: {path}")
    return value


def _verify_schema(path: Path) -> None:
    schema = _load(path)
    if schema.get("$id") != "urn:work-bundle:wor108:closure-contracts:v1":
        raise VerificationError("closure schema identity mismatch")
    if schema.get("additionalProperties") is not False:
        raise VerificationError("closure schema must be closed")
    fixture = schema.get("$defs", {}).get("fixture", {})
    if fixture.get("additionalProperties") is not False or set(fixture.get("required", [])) != FIXTURE_KEYS:
        raise VerificationError("fixture schema is not a closed required shape")


def _verify_fixtures(path: Path) -> tuple[str, ...]:
    package = _load(path)
    if set(package) != {"contract", "evaluation_id", "fixtures"}:
        raise VerificationError("fixture package closed shape mismatch")
    if package["contract"] != "wor108-closure-fixtures-v1" or package["evaluation_id"] != "wor108-legacy-closure-v1":
        raise VerificationError("fixture package identity mismatch")
    fixtures = package["fixtures"]
    if not isinstance(fixtures, list):
        raise VerificationError("fixtures must be an array")
    fixture_ids = tuple(item.get("fixture_id") for item in fixtures if isinstance(item, dict))
    if fixture_ids != EXPECTED_IDS:
        raise VerificationError("fixture IDs must be exactly RF-01..08, SG-01..08, CTX-01..06 in order")
    seen_nodes: set[str] = set()
    for item in fixtures:
        if set(item) != FIXTURE_KEYS:
            raise VerificationError(f"fixture closed shape mismatch: {item.get('fixture_id')}")
        fixture_id = item["fixture_id"]
        if item["area"] != EXPECTED_AREAS[fixture_id.split("-", 1)[0]]:
            raise VerificationError(f"fixture area mismatch: {fixture_id}")
        if item["oracle"] != "pytest" or item["expected"] != "passed" or not item["title"]:
            raise VerificationError(f"fixture oracle mismatch: {fixture_id}")
        nodes = item["pytest_nodes"]
        if not isinstance(nodes, list) or not nodes or len(nodes) != len(set(nodes)):
            raise VerificationError(f"fixture pytest node set mismatch: {fixture_id}")
        for node in nodes:
            match = NODE.fullmatch(node)
            if match is None:
                raise VerificationError(f"invalid pytest node: {node}")
            test_path = REPO_ROOT / match.group(1)
            if not test_path.is_file() or f"def {match.group(2)}(" not in test_path.read_text(encoding="utf-8"):
                raise VerificationError(f"pytest oracle does not resolve: {node}")
            if node in seen_nodes:
                raise VerificationError(f"pytest oracle assigned to multiple identities: {node}")
            seen_nodes.add(node)
    return fixture_ids


def _verify_migration(path: Path, fixture_ids: tuple[str, ...]) -> int:
    manifest = _load(path)
    if set(manifest) != MIGRATION_KEYS:
        raise VerificationError("migration-impact closed shape mismatch")
    if (manifest["contract"], manifest["issue"], manifest["evaluation_id"]) != (
        "wor108-migration-impact-v1", "WOR-108", "wor108-legacy-closure-v1"
    ):
        raise VerificationError("migration-impact identity mismatch")
    if manifest["accepted_legacy_baseline"] != {
        "commit": "9dce5df221485174d6179f713e8b179bbc20567a",
        "tree": "5a1f38355eae8068bab528923e807ce54e6f6fe5",
    }:
        raise VerificationError("accepted WOR-105 baseline mismatch")
    surfaces = manifest["changed_surfaces"]
    if not isinstance(surfaces, dict) or set(surfaces) != SURFACE_KEYS:
        raise VerificationError("changed surface classes mismatch")
    flattened = [surface for group in surfaces.values() for surface in group]
    if len(flattened) != len(set(flattened)) or any(not (REPO_ROOT / surface).is_file() for surface in flattened):
        raise VerificationError("changed surfaces must be unique existing files")
    if tuple(manifest["evaluation_identities"]) != fixture_ids:
        raise VerificationError("migration evaluation identities mismatch")
    if manifest["handoff_constraints"] != {
        "final_git_identity": "post_acceptance_handoff_only",
        "advance_wor107": False,
        "touch_work_bundle_mcp": False,
    }:
        raise VerificationError("migration handoff constraints mismatch")
    forbidden_identity_fields = {"accepted_head", "accepted_tree", "final_commit", "final_tree"}
    if forbidden_identity_fields.intersection(manifest):
        raise VerificationError("self-referential final Git identity is forbidden")
    return len(flattened)


def verify(
    fixtures_path: Path = EVAL_ROOT / "fixtures.json",
    migration_path: Path = EVAL_ROOT / "migration-impact.json",
    schema_path: Path = EVAL_ROOT / "contracts-v1.schema.json",
) -> dict[str, Any]:
    _verify_schema(schema_path)
    fixture_ids = _verify_fixtures(fixtures_path)
    surfaces = _verify_migration(migration_path, fixture_ids)
    return {
        "evaluation_id": "wor108-legacy-closure-v1",
        "fixtures": len(fixture_ids),
        "changed_surfaces": surfaces,
        "verdict": "accepted",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=EVAL_ROOT / "fixtures.json")
    parser.add_argument("--migration-impact", type=Path, default=EVAL_ROOT / "migration-impact.json")
    parser.add_argument("--schema", type=Path, default=EVAL_ROOT / "contracts-v1.schema.json")
    args = parser.parse_args()
    print(json.dumps(verify(args.fixtures, args.migration_impact, args.schema), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
