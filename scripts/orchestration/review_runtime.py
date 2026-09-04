#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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
    _nonempty(reviewer["capability"], "reviewer.capability")
    for field in PARTICIPATION_FIELDS:
        _enum(reviewer[field], {"none", "present"}, f"reviewer.{field}")
    _enum(reviewer["context_origin"], {"direct_source", "carried_summary"}, "reviewer.context_origin")

    evidence = _mapping(record["evidence"], "evidence")
    _closed(evidence, REVIEW_EVIDENCE_KEYS, "evidence")
    _enum(evidence["mode"], {"direct", "constrained_direct"}, "evidence.mode")
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
        if reviewer["context_origin"] != "direct_source":
            raise ReviewContractError("accepted review requires reviewer.context_origin: direct_source")
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


def validate_stage_reviews(values: Sequence[Mapping[str, Any]]) -> dict[str, StageReviewV1]:
    records = [validate_stage_review(value) for value in values]
    ids = [record.review_id for record in records]
    if len(ids) != len(set(ids)):
        raise ReviewContractError("stage review IDs must be globally unique")
    countable: dict[str, StageReviewV1] = {}
    for record in sorted(records, key=lambda item: item.completed_at):
        if record.verdict == "accepted" and record.staleness["is_stale"] is False:
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
