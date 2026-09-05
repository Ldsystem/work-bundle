#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")

FINDING_STAGES = frozenset({"specification", "plan", "implementation", "validation", "environment"})
FINDING_SEVERITIES = frozenset({"blocking", "non_blocking", "advisory"})
OBLIGATION_BASES = frozenset({"accepted_requirement", "essential_safety", "evidence_integrity", "none"})
TERMINAL_FINDING_DISPOSITIONS = frozenset({"accepted", "rejected"})
STAGE_REVIEW_STAGES = frozenset({"specification", "plan", "integrated_implementation"})
REVIEW_VERDICTS = frozenset({"accepted", "repair", "blocked"})
PARTICIPATION_FIELDS = (
    "authorship",
    "repair_participation",
    "decision_participation",
    "deliberation_participation",
)

ROUTES: dict[str, tuple[str, str, str]] = {
    "specification_gap": ("specification", "specification_owner", "reopen_specification"),
    "decomposition_gap": ("plan", "plan_owner", "repair_plan"),
    "allocation_gap": ("plan", "plan_owner", "reslice_plan"),
    "implementation_defect": ("implementation", "task_owner", "repair_task"),
    "validation_oracle_defect": ("validation_oracle", "oracle_owner", "repair_oracle"),
    "environment_failure": ("environment", "environment_owner", "recover_environment"),
    "advisory_enhancement": ("implementation", "backlog_owner", "record_advisory"),
}

FINDING_KEYS = frozenset(
    {
        "finding_id",
        "stage",
        "class",
        "severity",
        "first_broken_artifact",
        "obligation_basis",
        "evidence",
        "target_identity",
        "summary",
        "recommended_owner",
        "disposition",
    }
)
TARGET_KEYS = frozenset({"artifact_id", "revision", "sha256", "source_tree"})
EVIDENCE_ITEM_KEYS = frozenset({"kind", "locator", "digest_or_identity", "observation"})
STAGE_REVIEW_KEYS = frozenset(
    {"review_id", "stage", "target_identity", "reviewer", "evidence", "verdict", "findings", "started_at", "completed_at", "staleness"}
)
REVIEWER_KEYS = frozenset(
    {"agent_id", "capability", *PARTICIPATION_FIELDS, "context_origin"}
)
REVIEW_EVIDENCE_KEYS = frozenset({"mode", "capabilities", "unavailable_evidence", "commands", "artifacts"})
COMMAND_KEYS = frozenset({"command_id", "purpose", "exit_code", "output_digest"})
ARTIFACT_KEYS = frozenset({"path", "sha256"})
STALENESS_KEYS = frozenset({"is_stale", "reason", "supersedes"})


class ReviewContractError(ValueError):
    pass


def artifact_review_identity(path: Path, *, content: str | None = None) -> dict[str, Any]:
    """Semantic artifact identity; only lifecycle bookkeeping is non-semantic.

    Body, version, links, validation definitions and all other metadata remain bound.
    This permits the approved status transition without invalidating its own review.
    """
    from execution_context import parse_yaml_subset
    text = path.read_text(encoding="utf-8") if content is None else content.rstrip() + "\n"
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise SystemExit(f"stage review: missing artifact front matter: {path}")
    raw, body = text[4:].split("\n---\n", 1)
    metadata = parse_yaml_subset(raw)
    if not isinstance(metadata, dict) or not metadata.get("id"):
        raise SystemExit(f"stage review: missing artifact identity: {path}")
    semantic = {key: value for key, value in metadata.items() if key not in {
        "status", "last_updated", "updated_at",
    }}
    payload = json.dumps([semantic, body], sort_keys=True, default=str, separators=(",", ":"))
    return {"artifact_id": str(metadata["id"]), "revision": str(metadata.get("version", "1")),
            "sha256": hashlib.sha256(payload.encode()).hexdigest(), "source_tree": None}


def _require_current_review(root: Path, stage: str, identity: Mapping[str, Any]) -> None:
    """Read native records; historical prose is not an acceptance envelope."""
    accepted = []
    review_ids: set[str] = set()
    review_root = root / ".work-bundle/orchestration/reviews"
    try:
        for path in sorted(review_root.rglob("*")):
            if path.suffix not in {".json", ".yaml", ".yml"} or not path.is_file():
                continue
            if not path.resolve().is_relative_to(review_root.resolve()):
                raise ReviewContractError("review record escapes review store")
            value = _read_document(path)
            if not isinstance(value, dict) or "review_id" not in value or "stage" not in value:
                continue
            # Old target records remain history, not current acceptance candidates.
            # In particular, a superseded legacy evidence mode must not poison a
            # valid replacement review for the actual current artifact.
            if value["stage"] != stage or value.get("target_identity") != identity:
                continue
            record = validate_stage_review(value)
            if record.review_id in review_ids:
                raise ReviewContractError("stage review IDs must be globally unique")
            review_ids.add(record.review_id)
            if record.stage == stage and record.target_identity == identity:
                accepted.append(record)
        latest_time = max((_rfc3339_utc(item.completed_at, "completed_at") for item in accepted), default=None)
        latest = [item for item in accepted if _rfc3339_utc(item.completed_at, "completed_at") == latest_time]
        if latest and all(item.verdict == "accepted" and not item.staleness["is_stale"] for item in latest):
            return
    except (ValueError, OSError) as error:
        raise SystemExit(f"stage review blocked: {error}") from error
    raise SystemExit(f"stage review blocked: fresh accepted {stage} review required for {dict(identity)}")


def require_specification_review(root: Path, path: Path, *, content: str | None = None) -> None:
    if not path.resolve().is_relative_to((root / ".work-bundle/orchestration/spec").resolve()):
        raise SystemExit("stage review: specification escapes spec store")
    _require_current_review(root, "specification", artifact_review_identity(path, content=content))


def plan_review_identity(root: Path, plan_path: Path, *, content: str | None = None) -> dict[str, Any]:
    from execution_context import _read_structured, _resolve_spec_paths, parse_yaml_subset
    plan_root = root / ".work-bundle/orchestration/plan"
    if not plan_path.resolve().is_relative_to(plan_root.resolve()):
        raise SystemExit("stage review: root plan escapes plan store")
    identity = artifact_review_identity(plan_path, content=content)
    members = {str(plan_path.relative_to(plan_root)): identity["sha256"]}
    for path in sorted(plan_root.rglob("*.md")):
        if path == plan_path:
            continue
        if not path.resolve().is_relative_to(plan_root.resolve()):
            raise SystemExit("stage review: plan member escapes plan store")
        data, _ = _read_structured(path)
        if str(data.get("plan_id", "")) != identity["artifact_id"]:
            continue
        members[str(path.relative_to(plan_root))] = artifact_review_identity(path)["sha256"]
    plan_data = (_read_structured(plan_path)[0] if content is None
                 else parse_yaml_subset(content.split("---", 2)[1]))
    specifications = [artifact_review_identity(path) for path in _resolve_spec_paths(root, {}, plan_data)]
    payload = {"members": members, "specifications": specifications}
    identity["sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return identity


def require_plan_reviews(root: Path, plan_path: Path, *, source_root: Path | None = None,
                         content: str | None = None) -> None:
    from execution_context import _read_structured, _resolve_spec_paths, parse_yaml_subset
    data = (_read_structured(plan_path)[0] if content is None
            else parse_yaml_subset(content.split("---", 2)[1]))
    for spec in _resolve_spec_paths(root, {}, data):
        require_specification_review(root, spec)
    identity = plan_review_identity(root, plan_path, content=content)
    _require_current_review(root, "plan", identity)
    if source_root is not None:
        def git(*args: str) -> str:
            result = subprocess.run(["git", "-C", str(source_root), *args], capture_output=True, text=True)
            if result.returncode:
                raise SystemExit("stage review: final source repository unavailable")
            return result.stdout.strip()
        if git("status", "--porcelain", "--untracked-files=all"):
            raise SystemExit("stage review: final source must be clean, including untracked files")
        final = dict(identity, source_tree=git("rev-parse", "HEAD^{tree}"))
        _require_current_review(root, "integrated_implementation", final)


@dataclass(frozen=True)
class ReviewFindingV1:
    finding_id: str
    stage: str
    finding_class: str
    severity: str
    first_broken_artifact: str
    obligation_basis: str
    evidence: tuple[Mapping[str, Any], ...]
    target_identity: Mapping[str, Any]
    summary: str
    recommended_owner: str
    disposition: str


@dataclass(frozen=True)
class StageReviewV1:
    review_id: str
    stage: str
    target_identity: Mapping[str, Any]
    reviewer: Mapping[str, Any]
    evidence: Mapping[str, Any]
    verdict: str
    findings: tuple[ReviewFindingV1, ...]
    started_at: str
    completed_at: str
    staleness: Mapping[str, Any]


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewContractError(f"{name} must be an object")
    return value


def _closed(record: Mapping[str, Any], required: frozenset[str], name: str) -> None:
    missing = sorted(required - record.keys())
    unknown = sorted(record.keys() - required)
    if missing:
        raise ReviewContractError(f"{name} missing required fields: {', '.join(missing)}")
    if unknown:
        raise ReviewContractError(f"{name} contains unknown fields: {', '.join(unknown)}")


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewContractError(f"{name} must be a non-empty string")
    return value


def _identifier(value: Any, name: str) -> str:
    text = _nonempty(value, name)
    if not ID_RE.fullmatch(text):
        raise ReviewContractError(f"{name} is not a valid id")
    return text


def _enum(value: Any, allowed: frozenset[str] | set[str], name: str) -> str:
    if value not in allowed:
        raise ReviewContractError(f"{name} must be one of: {', '.join(sorted(allowed))}")
    return str(value)


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ReviewContractError(f"{name} must be a list of non-empty strings")
    return value


def _rfc3339_utc(value: Any, name: str) -> datetime:
    text = _nonempty(value, name)
    if not text.endswith("Z"):
        raise ReviewContractError(f"{name} must be RFC3339 UTC")
    try:
        return datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ReviewContractError(f"{name} must be RFC3339 UTC") from error


def _target_identity(value: Any, name: str = "target_identity") -> Mapping[str, Any]:
    target = _mapping(value, name)
    _closed(target, TARGET_KEYS, name)
    _identifier(target["artifact_id"], f"{name}.artifact_id")
    _nonempty(target["revision"], f"{name}.revision")
    if not isinstance(target["sha256"], str) or not SHA256_RE.fullmatch(target["sha256"]):
        raise ReviewContractError(f"{name}.sha256 must be a lowercase SHA-256")
    source_tree = target["source_tree"]
    if source_tree is not None and (not isinstance(source_tree, str) or not GIT_OID_RE.fullmatch(source_tree)):
        raise ReviewContractError(f"{name}.source_tree must be a Git object id or null")
    return target


def classify_first_broken_owner(finding_class: str) -> tuple[str, str, str]:
    try:
        return ROUTES[finding_class]
    except KeyError as error:
        raise ReviewContractError(f"class is not classified: {finding_class}") from error


def validate_review_finding(value: Mapping[str, Any]) -> ReviewFindingV1:
    record = _mapping(value, "review_finding_v1")
    _closed(record, FINDING_KEYS, "review_finding_v1")
    finding_id = _identifier(record["finding_id"], "finding_id")
    stage = _enum(record["stage"], FINDING_STAGES, "stage")
    finding_class = _enum(record["class"], set(ROUTES), "class")
    severity = _enum(record["severity"], FINDING_SEVERITIES, "severity")
    obligation_basis = _enum(record["obligation_basis"], OBLIGATION_BASES, "obligation_basis")
    expected_artifact, expected_owner, expected_disposition = classify_first_broken_owner(finding_class)
    if record["first_broken_artifact"] != expected_artifact or record["recommended_owner"] != expected_owner:
        raise ReviewContractError("review finding routing does not match the first broken artifact and owner")
    disposition = _enum(
        record["disposition"],
        {expected_disposition, *TERMINAL_FINDING_DISPOSITIONS},
        "disposition",
    )
    evidence_raw = record["evidence"]
    if not isinstance(evidence_raw, list):
        raise ReviewContractError("evidence must be a list")
    evidence: list[Mapping[str, Any]] = []
    for index, raw_item in enumerate(evidence_raw):
        item = _mapping(raw_item, f"evidence[{index}]")
        _closed(item, EVIDENCE_ITEM_KEYS, f"evidence[{index}]")
        _enum(item["kind"], {"authority", "source", "test", "runtime", "environment"}, f"evidence[{index}].kind")
        for key in ("locator", "digest_or_identity", "observation"):
            _nonempty(item[key], f"evidence[{index}].{key}")
        evidence.append(item)
    if severity == "blocking" and (obligation_basis == "none" or not evidence):
        raise ReviewContractError("blocking finding requires a non-none obligation basis and evidence")
    if finding_class == "advisory_enhancement" and severity == "blocking":
        raise ReviewContractError("advisory_enhancement cannot be blocking without accepted reclassification")
    target = _target_identity(record["target_identity"])
    summary = _nonempty(record["summary"], "summary")
    return ReviewFindingV1(
        finding_id,
        stage,
        finding_class,
        severity,
        expected_artifact,
        obligation_basis,
        tuple(evidence),
        target,
        summary,
        expected_owner,
        disposition,
    )


def route_review_verdict(
    value: Mapping[str, Any], *, previous_scope_expansions: int = 0
) -> dict[str, Any]:
    finding = validate_review_finding(value)
    expected_action = ROUTES[finding.finding_class][2]
    if finding.disposition in TERMINAL_FINDING_DISPOSITIONS:
        raise ReviewContractError("terminal adjudicator disposition cannot authorize repair mutation")
    if finding.disposition != expected_action:
        raise ReviewContractError("review finding routing disposition is invalid")
    repeated_reslice = expected_action == "reslice_plan" and previous_scope_expansions > 0
    return {
        "finding_id": finding.finding_id,
        "first_broken_artifact": finding.first_broken_artifact,
        "return_to": finding.recommended_owner,
        "action": expected_action,
        "execution_state": "paused_for_reslice" if repeated_reslice else "returned_for_repair",
        "preserve_valid_work_and_evidence": True,
        "silent_expansion_allowed": False,
    }


def transition_review_finding(
    value: Mapping[str, Any], disposition: str
) -> ReviewFindingV1:
    finding = validate_review_finding(value)
    if finding.disposition in TERMINAL_FINDING_DISPOSITIONS:
        raise ReviewContractError("terminal review finding disposition cannot transition")
    if disposition not in TERMINAL_FINDING_DISPOSITIONS:
        raise ReviewContractError("finding lifecycle transition requires an adjudicator disposition")
    updated = dict(value)
    updated["disposition"] = disposition
    return validate_review_finding(updated)


def validate_stage_review(
    value: Mapping[str, Any], *, current_target_identity: Mapping[str, Any] | None = None
) -> StageReviewV1:
    record = _mapping(value, "stage_review_v1")
    _closed(record, STAGE_REVIEW_KEYS, "stage_review_v1")
    review_id = _identifier(record["review_id"], "review_id")
    stage = _enum(record["stage"], STAGE_REVIEW_STAGES, "stage")
    target = _target_identity(record["target_identity"])
    reviewer = _mapping(record["reviewer"], "reviewer")
    _closed(reviewer, REVIEWER_KEYS, "reviewer")
    _identifier(reviewer["agent_id"], "reviewer.agent_id")
    _enum(reviewer["capability"], {"standard", "judgment"}, "reviewer.capability")
    for field in PARTICIPATION_FIELDS:
        _enum(reviewer[field], {"none", "present"}, f"reviewer.{field}")
    _enum(reviewer["context_origin"], {"direct_source", "reproducible_snapshot", "packet_only", "carried_summary"}, "reviewer.context_origin")

    evidence = _mapping(record["evidence"], "evidence")
    _closed(evidence, REVIEW_EVIDENCE_KEYS, "evidence")
    _enum(evidence["mode"], {"direct_source", "reproducible_snapshot", "packet_only", "direct", "constrained_direct"}, "evidence.mode")
    _string_list(evidence["capabilities"], "evidence.capabilities")
    _string_list(evidence["unavailable_evidence"], "evidence.unavailable_evidence")
    commands = evidence["commands"]
    artifacts = evidence["artifacts"]
    if not isinstance(commands, list) or not isinstance(artifacts, list):
        raise ReviewContractError("evidence commands and artifacts must be lists")
    for index, raw_command in enumerate(commands):
        command = _mapping(raw_command, f"evidence.commands[{index}]")
        _closed(command, COMMAND_KEYS, f"evidence.commands[{index}]")
        _identifier(command["command_id"], f"evidence.commands[{index}].command_id")
        _nonempty(command["purpose"], f"evidence.commands[{index}].purpose")
        if not isinstance(command["exit_code"], int) or isinstance(command["exit_code"], bool):
            raise ReviewContractError(f"evidence.commands[{index}].exit_code must be an integer")
        if not isinstance(command["output_digest"], str) or not SHA256_RE.fullmatch(command["output_digest"]):
            raise ReviewContractError(f"evidence.commands[{index}].output_digest must be a lowercase SHA-256")
    for index, raw_artifact in enumerate(artifacts):
        artifact = _mapping(raw_artifact, f"evidence.artifacts[{index}]")
        _closed(artifact, ARTIFACT_KEYS, f"evidence.artifacts[{index}]")
        _nonempty(artifact["path"], f"evidence.artifacts[{index}].path")
        if not isinstance(artifact["sha256"], str) or not SHA256_RE.fullmatch(artifact["sha256"]):
            raise ReviewContractError(f"evidence.artifacts[{index}].sha256 must be a lowercase SHA-256")

    verdict = _enum(record["verdict"], REVIEW_VERDICTS, "verdict")
    findings_raw = record["findings"]
    if not isinstance(findings_raw, list):
        raise ReviewContractError("findings must be a list")
    findings = tuple(validate_review_finding(_mapping(item, "finding")) for item in findings_raw)
    started = _rfc3339_utc(record["started_at"], "started_at")
    completed = _rfc3339_utc(record["completed_at"], "completed_at")
    if completed < started:
        raise ReviewContractError("completed_at must not precede started_at")
    staleness = _mapping(record["staleness"], "staleness")
    _closed(staleness, STALENESS_KEYS, "staleness")
    if not isinstance(staleness["is_stale"], bool):
        raise ReviewContractError("staleness.is_stale must be boolean")
    reason = staleness["reason"]
    supersedes = staleness["supersedes"]
    if reason is not None:
        _nonempty(reason, "staleness.reason")
    if supersedes is not None:
        _identifier(supersedes, "staleness.supersedes")
    if staleness["is_stale"] and reason is None:
        raise ReviewContractError("stale review requires staleness.reason")
    if not staleness["is_stale"] and reason is not None:
        raise ReviewContractError("current review cannot carry a staleness.reason")
    if current_target_identity is not None:
        current = _target_identity(current_target_identity, "current_target_identity")
        changed = any(target[key] != current[key] for key in TARGET_KEYS)
        if changed and not staleness["is_stale"]:
            raise ReviewContractError("review target changed and the review must be stale")
        if not changed and staleness["is_stale"]:
            raise ReviewContractError("review target is unchanged but the review is marked stale")
    if verdict == "accepted":
        blocking = [item.finding_id for item in findings if item.severity == "blocking"]
        if blocking:
            raise ReviewContractError("accepted review cannot contain blocking findings")
        for field in PARTICIPATION_FIELDS:
            if reviewer[field] != "none":
                raise ReviewContractError(f"accepted review requires reviewer.{field}: none")
        if reviewer["context_origin"] not in {"direct_source", "reproducible_snapshot"}:
            raise ReviewContractError("accepted review requires direct_source or reproducible_snapshot context")
        if evidence["mode"] in {"packet_only", "constrained_direct"} or evidence["unavailable_evidence"]:
            raise ReviewContractError("accepted review requires complete claim-relevant evidence, not packet-only or constrained evidence")
        if evidence["mode"] == "reproducible_snapshot" or reviewer["context_origin"] == "reproducible_snapshot":
            if evidence["mode"] != "reproducible_snapshot" or not artifacts:
                raise ReviewContractError("snapshot review requires explicit reproducible_snapshot artifacts")
    return StageReviewV1(
        review_id,
        stage,
        target,
        reviewer,
        evidence,
        verdict,
        findings,
        str(record["started_at"]),
        str(record["completed_at"]),
        staleness,
    )


def validate_stage_reviews(
    values: Sequence[Mapping[str, Any]], *,
    current_target_identities: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, StageReviewV1]:
    if current_target_identities is None or set(current_target_identities) != STAGE_REVIEW_STAGES:
        raise ReviewContractError("actual current target identities are required for all three stages")
    records = [validate_stage_review(value) for value in values]
    ids = [record.review_id for record in records]
    if len(ids) != len(set(ids)):
        raise ReviewContractError("stage review IDs must be globally unique")
    countable: dict[str, StageReviewV1] = {}
    for record in sorted(records, key=lambda item: item.completed_at):
        current = _target_identity(current_target_identities[record.stage], "current_target_identity")
        if record.target_identity == current:
            countable.pop(record.stage, None)
        if record.verdict == "accepted" and record.staleness["is_stale"] is False and record.target_identity == current:
            countable[record.stage] = record
    if set(countable) != STAGE_REVIEW_STAGES or len(countable) != 3:
        raise ReviewContractError("exactly three mandatory stage identities must have current accepted reviews")
    return countable


def validate_contract_instance(definition: str, value: Mapping[str, Any]) -> ReviewFindingV1 | StageReviewV1:
    if definition in {"reviewFinding", "review_finding_v1", "API-001"}:
        return validate_review_finding(value)
    if definition in {"stageReview", "stage_review_v1", "API-002"}:
        return validate_stage_review(value)
    raise ReviewContractError(f"unsupported contract definition: {definition}")


def _read_document(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as error:
            raise ReviewContractError("YAML input requires PyYAML") from error
        value = yaml.safe_load(text)
    return _mapping(value, str(path))


def _validate_schema_definition(schema: Mapping[str, Any], definition: str, value: Mapping[str, Any]) -> None:
    definitions = _mapping(schema.get("$defs"), "$defs")
    if definition not in definitions:
        raise ReviewContractError(f"schema definition not found: {definition}")
    if definition in {"reviewFinding", "stageReview"}:
        validate_contract_instance(definition, value)
    try:
        from jsonschema import Draft202012Validator
    except ImportError as error:
        if definition in {"reviewFinding", "stageReview"}:
            return
        raise ReviewContractError(f"contract definition requires jsonschema: {definition}") from error
    document = dict(schema)
    document["$ref"] = f"#/$defs/{definition}"
    errors = sorted(Draft202012Validator(document).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        raise ReviewContractError(errors[0].message)


def cmd_validate_contract(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="review_runtime.py validate-contract")
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--definition", required=True)
    parser.add_argument("--instance", type=Path, required=True)
    parsed = parser.parse_args(argv)
    try:
        schema = _read_document(parsed.schema)
        instance = _read_document(parsed.instance)
        _validate_schema_definition(schema, parsed.definition, instance)
    except (OSError, ReviewContractError) as error:
        print(json.dumps({"status": "blocked", "failure_code": "WB_REVIEW_CONTRACT_INVALID", "detail": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"status": "passed", "definition": parsed.definition, "instance": str(parsed.instance)}, sort_keys=True))
    return 0


def cmd_assert_migration_stop(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="review_runtime.py assert-migration-stop")
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--required-excluded", nargs="+", required=True)
    parsed = parser.parse_args(argv)
    try:
        instance = _read_document(parsed.instance)
        if instance.get("issue") != "WOR-107":
            raise ReviewContractError("migration handoff issue must be WOR-107")
        excluded = instance.get("excluded_work")
        if not isinstance(excluded, list) or any(not isinstance(item, str) for item in excluded):
            raise ReviewContractError("excluded_work must be a list of strings")
        missing = [item for item in parsed.required_excluded if item not in excluded]
        if missing:
            raise ReviewContractError(f"migration stop boundary missing exclusions: {', '.join(missing)}")
    except (OSError, ReviewContractError) as error:
        print(json.dumps({"status": "blocked", "failure_code": "WB_MIGRATION_STOP_BOUNDARY_INVALID", "detail": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"status": "passed", "issue": "WOR-107", "excluded_work": parsed.required_excluded}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review_runtime.py")
    parser.add_argument("command", choices=("validate-contract", "assert-migration-stop"))
    parsed, remaining = parser.parse_known_args(argv)
    if parsed.command == "validate-contract":
        return cmd_validate_contract(remaining)
    return cmd_assert_migration_stop(remaining)


if __name__ == "__main__":
    raise SystemExit(main())
