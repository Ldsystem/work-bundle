#!/usr/bin/env python3
"""Independent deterministic verifier for the WOR-109 closure package."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
BASELINE = {"commit": "cfa089f0d2ed211b98d049eb37bfcdccb8091516", "tree": "12e4a696c3caf991654f0b9ac9ef40594699c8d4"}
EXPECTED_IDS = tuple(f"PD-{i:02d}" for i in range(1, 15))
SOURCE_IDS = {"REQ-PD-001", "REQ-PD-002", "REQ-PD-003", "REQ-PD-004", "REQ-PD-005", "REQ-PD-006", "REQ-SPEC-001", "REQ-LW-001", "REQ-LW-002", "REQ-LW-003", "CON-003"}
FIXTURE_KEYS = {"id", "scenario", "oracle", "source_ids", "pytest_node"}
MIGRATION_KEYS = {"contract", "issue", "baseline", "accepted_worktree", "changed_surfaces", "semantic_deltas", "parity_owners", "epoch1_evidence", "evaluation", "exclusions"}
CATEGORIES = {"skills", "rules", "contracts", "runtime_operations", "artifact_semantics", "evaluations"}
OPERATIONS = {"added", "modified", "deleted"}
NODE = re.compile(r"^tests/test_wor109_[a-z_]+\.py::test_[a-z0-9_]+$")

class VerificationError(RuntimeError):
    pass

def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError(f"object required: {path}")
    return value

def _verify_schema(path: Path) -> None:
    schema = _load(path)
    if schema.get("$id") != "urn:work-bundle:wor109:closure-contracts:v1" or schema.get("additionalProperties") is not False:
        raise VerificationError("closure schema identity or closed shape mismatch")
    fixture = schema.get("properties", {}).get("fixture", {})
    if fixture.get("additionalProperties") is not False or set(fixture.get("required", [])) != FIXTURE_KEYS:
        raise VerificationError("fixture schema is not closed")

def _verify_fixtures(path: Path) -> tuple[str, ...]:
    package = _load(path)
    if set(package) != {"contract", "evaluation_id", "fixtures"} or package["contract"] != "wor109-closure-fixtures-v1" or package["evaluation_id"] != "wor109-review-stable-orchestration-v1":
        raise VerificationError("fixture package identity or shape mismatch")
    fixtures = package["fixtures"]
    if not isinstance(fixtures, list) or tuple(item.get("id") for item in fixtures if isinstance(item, dict)) != EXPECTED_IDS:
        raise VerificationError("fixture IDs must be exactly PD-01..PD-14")
    nodes: set[str] = set()
    for item in fixtures:
        if set(item) != FIXTURE_KEYS or not item["scenario"] or not item["oracle"]:
            raise VerificationError(f"fixture closed shape mismatch: {item.get('id')}")
        if not isinstance(item["source_ids"], list) or not item["source_ids"] or not set(item["source_ids"]).issubset(SOURCE_IDS):
            raise VerificationError(f"fixture source authority mismatch: {item['id']}")
        node = item["pytest_node"]
        if not NODE.fullmatch(node) or node in nodes:
            raise VerificationError(f"invalid or duplicate pytest node: {node}")
        semantic_prefix = (
            "tests/test_wor109_planner_scenarios.py::"
            f"test_pd_{item['id'][3:]}_"
        )
        if not node.startswith(semantic_prefix):
            raise VerificationError(f"semantic oracle binding mismatch: {item['id']}")
        nodes.add(node)
        test_path, function = node.split("::")
        source = REPO_ROOT / test_path
        if not source.is_file() or f"def {function}(" not in source.read_text(encoding="utf-8"):
            raise VerificationError(f"pytest oracle does not resolve: {node}")
    return EXPECTED_IDS

def _git_changed() -> dict[str, str]:
    proc = subprocess.run(["git", "-C", str(REPO_ROOT), "diff", "--name-status", BASELINE["commit"], "HEAD", "--"], capture_output=True, text=True, check=False)
    if proc.returncode:
        raise VerificationError("baseline delta unavailable")
    result: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        status, path = line.split("\t", 1)
        result[path] = {"A": "added", "M": "modified", "D": "deleted"}.get(status, "modified")
    return result

def _verify_migration(path: Path, fixture_ids: tuple[str, ...]) -> int:
    manifest = _load(path)
    if set(manifest) != MIGRATION_KEYS or manifest["contract"] != "wor109-migration-impact-v1" or manifest["issue"] != "WOR-109" or manifest["baseline"] != BASELINE:
        raise VerificationError("migration identity or closed shape mismatch")
    accepted = manifest["accepted_worktree"]
    if set(accepted) != {"commit", "tree", "status"} or accepted["commit"] != "3cf749bbb34b208ca852a5b77bcf26645a50d4cb" or accepted["tree"] != "e343bf27f41996bd8189949ae6749f48abc09652":
        raise VerificationError("accepted pre-commit worktree mismatch")
    surfaces = manifest["changed_surfaces"]
    if set(surfaces) != OPERATIONS or any(set(group) != CATEGORIES for group in surfaces.values()):
        raise VerificationError("changed surface dimensions mismatch")
    listed: dict[str, str] = {}
    for op, groups in surfaces.items():
        for category, paths in groups.items():
            if not isinstance(paths, list) or paths != sorted(set(paths)):
                raise VerificationError("changed surfaces must be sorted and unique")
            for rel in paths:
                if rel in listed or (op != "deleted" and not (REPO_ROOT / rel).is_file()):
                    raise VerificationError(f"invalid changed surface: {rel}")
                listed[rel] = op
    if listed != _git_changed():
        raise VerificationError("changed surface completeness mismatch")
    if set(manifest["semantic_deltas"]) != {"acceptance_authority", "planner_reslice", "specification_wording", "lightweight_scope", "historical_identity"}:
        raise VerificationError("semantic delta rows mismatch")
    for row in manifest["semantic_deltas"].values():
        if set(row) != {"source_ids", "affected_paths"} or not row["source_ids"] or not row["affected_paths"]:
            raise VerificationError("semantic delta row incomplete")
    telemetry_changed = any(path in listed for path in ("scripts/work-bundle/stage_events.py", "scripts/orchestration/review_runtime.py"))
    expected_parity = {"WOR-76", "WOR-78", "WOR-81", "WOR-82"} | ({"WOR-83"} if telemetry_changed else set())
    if set(manifest["parity_owners"]) != expected_parity or any(set(row) != {"status", "navigation"} or row["status"] != "likely" for row in manifest["parity_owners"].values()):
        raise VerificationError("parity owner rows mismatch")
    evidence = manifest["epoch1_evidence"]
    if set(evidence) != {"reusable", "invalidated"} or not isinstance(evidence["reusable"], list) or not isinstance(evidence["invalidated"], list):
        raise VerificationError("epoch-1 evidence partition mismatch")
    for row in evidence["invalidated"]:
        if set(row) != {"evidence_id", "reason", "replacement"} or not row["reason"] or not row["replacement"]:
            raise VerificationError("invalidated evidence requires reason and replacement")
    evaluation = manifest["evaluation"]
    if set(evaluation) != {"fixture_ids", "verifier_output_digest"} or tuple(evaluation["fixture_ids"]) != fixture_ids or not re.fullmatch(r"[0-9a-f]{64}", evaluation["verifier_output_digest"]):
        raise VerificationError("evaluation binding mismatch")
    exclusions = manifest["exclusions"]
    if set(exclusions) != {"work-bundle-mcp", "WOR-107", "WOR-79", "Step 00 mutation", "migration execution"} or any(row != {"authorized": False} for row in exclusions.values()):
        raise VerificationError("exclusion authorization mismatch")
    return len(listed)

def verify(fixtures_path: Path = EVAL_ROOT / "fixtures.json", migration_path: Path = EVAL_ROOT / "migration-impact.json", schema_path: Path = EVAL_ROOT / "contracts-v1.schema.json") -> dict[str, Any]:
    _verify_schema(schema_path)
    ids = _verify_fixtures(fixtures_path)
    changed = _verify_migration(migration_path, ids)
    return {"evaluation_id": "wor109-review-stable-orchestration-v1", "fixtures": len(ids), "changed_surfaces": changed, "verdict": "accepted"}

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
