#!/usr/bin/env python3
"""Independent verifier for normalized WOR-105 adversarial results."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
SHA = re.compile(r"^[0-9a-f]{64}$")
OID = re.compile(r"^[0-9a-f]{40}$")
RESULT_KEYS = {"fixture_id", "fixture_sha256", "expected_decision", "actual_decision", "product_tree", "specification_sha256", "plan_sha256", "task_identity", "evaluation_id", "component_digests", "raw_evidence_sha256", "adjudication_sha256", "event_ids", "proof", "passed"}
COMPONENT_KEYS = {"profile", "fixtures", "runner", "verifier", "result_schema", "semantic_schema", "instructions", "evidence_capabilities"}


class VerificationError(RuntimeError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(value: object) -> str:
    data = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_value(schema: dict[str, Any], value: Any, root: dict[str, Any], label: str) -> None:
    if "$ref" in schema:
        target: Any = root
        for token in schema["$ref"].removeprefix("#/").split("/"):
            target = target[token]
        _schema_value(target, value, root, label)
        return
    expected_type = schema.get("type")
    matches_type = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
    }
    if expected_type in matches_type and not matches_type[expected_type]:
        raise VerificationError(f"schema type mismatch: {label}")
    if "const" in schema and value != schema["const"]:
        raise VerificationError(f"schema constant mismatch: {label}")
    if "enum" in schema and value not in schema["enum"]:
        raise VerificationError(f"schema enum mismatch: {label}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise VerificationError(f"schema string length mismatch: {label}")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise VerificationError(f"schema pattern mismatch: {label}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            raise VerificationError(f"schema array length mismatch: {label}")
        if schema.get("uniqueItems") and len({_canonical(item) for item in value}) != len(value):
            raise VerificationError(f"schema array uniqueness mismatch: {label}")
        if "items" in schema:
            for index, item in enumerate(value):
                _schema_value(schema["items"], item, root, f"{label}[{index}]")
    if isinstance(value, dict):
        required = set(schema.get("required", []))
        if not required.issubset(value):
            raise VerificationError(f"schema required fields mismatch: {label}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and not set(value).issubset(properties):
            raise VerificationError(f"schema closed shape mismatch: {label}")
        if "propertyNames" in schema and not set(value).issubset(schema["propertyNames"].get("enum", [])):
            raise VerificationError(f"schema property names mismatch: {label}")
        for key, item_schema in properties.items():
            if key in value:
                _schema_value(item_schema, value[key], root, f"{label}.{key}")


def _verify_result_schema(manifest: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    schema_path = REPO_ROOT / manifest["components"]["result_schema"]["path"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("$id") != "urn:work-bundle:wor105:adversarial-result:v1":
        raise VerificationError("result schema identity mismatch")
    base = {key: value for key, value in schema.items() if key != "allOf"}
    branches = schema.get("allOf", [])
    branch_by_fixture = {
        item["if"]["properties"]["fixture_id"]["const"]: item["then"]
        for item in branches
    }
    if set(branch_by_fixture) != {f"ADV-{number:02d}" for number in range(1, 13)}:
        raise VerificationError("result schema branch set mismatch")
    for row in rows:
        _schema_value(base, row, schema, row["fixture_id"])
        _schema_value(branch_by_fixture[row["fixture_id"]], row, schema, row["fixture_id"])


def _load_fixtures(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    records = []
    aggregate_input = b""
    for item in manifest["fixtures"]:
        path = REPO_ROOT / item["path"]
        digest = _file_sha(path)
        if digest != item["sha256"]:
            raise VerificationError(f"fixture digest mismatch: {item['fixture_id']}")
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if fixture["fixture_id"] != item["fixture_id"]:
            raise VerificationError("fixture order or ID mismatch")
        aggregate_input += f"{fixture['fixture_id']}\0{digest}\n".encode()
        records.append((fixture, digest))
    if _sha(aggregate_input) != manifest["components"]["fixtures"]["sha256"]:
        raise VerificationError("fixture aggregate mismatch")
    return records


def _verify_components(manifest: dict[str, Any]) -> dict[str, str]:
    if set(manifest["components"]) != COMPONENT_KEYS:
        raise VerificationError("component set mismatch")
    for name, item in manifest["components"].items():
        if name == "fixtures":
            continue
        if _file_sha(REPO_ROOT / item["path"]) != item["sha256"]:
            raise VerificationError(f"component digest mismatch: {name}")
    return {name: item["sha256"] for name, item in manifest["components"].items()}


def _relations(row: dict[str, Any]) -> None:
    proof, fixture_id = row["proof"], row["fixture_id"]
    if fixture_id == "ADV-01":
        if proof["source_sentinel_before_sha256"] != proof["source_sentinel_after_sha256"] or proof["control_sentinel_before_sha256"] != proof["control_sentinel_after_sha256"]:
            raise VerificationError("ADV-01 sentinel mutation")
        if proof["denial_classes"] != ["permission_denied"] * 5 or len(set(proof["event_ids"])) != 2:
            raise VerificationError("ADV-01 denial/event cardinality")
    elif fixture_id == "ADV-04" and proof["stage_state_before_sha256"] != proof["stage_state_after_sha256"]:
        raise VerificationError("ADV-04 stage state mutation")
    elif fixture_id == "ADV-05":
        if proof["old_digest"] == proof["new_digest"] or proof["raw_response_before_sha256"] != proof["raw_response_after_sha256"] or proof["raw_trace_before_sha256"] != proof["raw_trace_after_sha256"]:
            raise VerificationError("ADV-05 invalidation/raw evidence relation")
    elif fixture_id == "ADV-06":
        if proof["product_tree_before"] != proof["product_tree_after"] or proof["observation_before_sha256"] != proof["observation_after_sha256"] or proof["packaging_before"] == proof["packaging_after"]:
            raise VerificationError("ADV-06 packaging relation")
    elif fixture_id == "ADV-08" and proof["observation_id"] != proof["reuse_of"]:
        raise VerificationError("ADV-08 reuse relation")
    elif fixture_id == "ADV-09" and proof["before_snapshot_sha256"] != proof["after_snapshot_sha256"]:
        raise VerificationError("ADV-09 binding mutation")
    elif fixture_id == "ADV-11" and proof["product_revision_before"] != proof["product_revision_after"]:
        raise VerificationError("ADV-11 product rollback")
    elif fixture_id == "ADV-12" and proof["first_apply_state_sha256"] != proof["replay_state_sha256"]:
        raise VerificationError("ADV-12 replay relation")


def verify_results(manifest_path: Path, results_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("enforcement_mode") != "native":
        raise VerificationError("native enforcement missing")
    components = _verify_components(manifest)
    fixtures = _load_fixtures(manifest)
    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 12 or len(fixtures) != 12:
        raise VerificationError("exactly twelve results required")
    _verify_result_schema(manifest, rows)
    if [row["fixture_id"] for row in rows] != [fixture["fixture_id"] for fixture, _ in fixtures]:
        raise VerificationError("result ordering mismatch")
    for row, (fixture, fixture_sha) in zip(rows, fixtures, strict=True):
        if set(row) != RESULT_KEYS or set(row.get("component_digests", {})) != COMPONENT_KEYS:
            raise VerificationError("result closed shape mismatch")
        if set(row.get("proof", {})) != set(fixture["proof_required"]):
            raise VerificationError(f"{row['fixture_id']} proof keys mismatch")
        if row["fixture_sha256"] != fixture_sha or row["component_digests"] != components:
            raise VerificationError("result component identity mismatch")
        if row["expected_decision"] != fixture["expected_decision"] or row["actual_decision"] != fixture["expected_decision"] or row["passed"] is not True:
            raise VerificationError("decision mismatch")
        if row["product_tree"] != manifest["product_tree"] or row["specification_sha256"] != manifest["specification_sha256"] or row["plan_sha256"] != manifest["plan_sha256"] or row["task_identity"] != manifest["task_identity"] or row["evaluation_id"] != manifest["evaluation_id"]:
            raise VerificationError("frozen identity mismatch")
        if not OID.fullmatch(row["product_tree"]):
            raise VerificationError("invalid product tree")
        digest_values = [row["fixture_sha256"], row["specification_sha256"], row["plan_sha256"], row["raw_evidence_sha256"], row["adjudication_sha256"], *row["component_digests"].values()]
        if not all(isinstance(value, str) and SHA.fullmatch(value) for value in digest_values):
            raise VerificationError("invalid digest")
        if row["raw_evidence_sha256"] != _sha(fixture["input"]) or row["adjudication_sha256"] != _sha(row["proof"]):
            raise VerificationError("raw/adjudication digest mismatch")
        _relations(row)
    return {"passed": 12, "total": 12, "verdict": "accepted"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_results(args.manifest, args.results), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
