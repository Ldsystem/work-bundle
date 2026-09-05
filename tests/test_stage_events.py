from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORK_BUNDLE_SCRIPTS = REPO_ROOT / "scripts" / "work-bundle"
if str(WORK_BUNDLE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WORK_BUNDLE_SCRIPTS))

from stage_events import (  # noqa: E402
    StageEventError,
    StageEventV1,
    append_stage_event,
    export_stage_events,
    query_stage_events,
    redact_event_payload,
    validate_stage_event,
)


EVENT_TYPES = (
    "stage_started",
    "stage_completed",
    "finding_recorded",
    "work_returned",
    "reslice_recorded",
    "suite_started",
    "suite_reused",
    "suite_completed",
    "evidence_invalidated",
    "reviewer_mutation_denied",
    "control_plane_repaired",
    "binding_retained",
    "binding_released",
)
FINDING_CLASSES = (
    "specification_gap",
    "decomposition_gap",
    "allocation_gap",
    "implementation_defect",
    "validation_oracle_defect",
    "environment_failure",
    "advisory_enhancement",
)


def event(event_id: str = "event-001", **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "event_id": event_id,
        "timestamp": "2026-09-05T01:02:03Z",
        "process_id": "process-001",
        "stage": "implementation",
        "attempt_id": "attempt-001",
        "event_type": "stage_started",
        "enforcement_mode": "bootstrap_policy",
        "join_ids": {
            "specification_id": "spec-001",
            "plan_id": "plan-001",
            "phase_id": "phase-b",
            "task_id": "task-b05",
            "review_id": None,
            "evaluation_id": None,
        },
        "clocks": {"wall_ms": 12, "active_ms": 8, "billed_ms": None},
        "finding_class": None,
        "return_reason": None,
        "owner": "task_owner",
        "identity": {
            "product_tree": "0" * 40,
            "artifact_digest": "1" * 64,
            "mutation_epoch": 0,
        },
        "privacy": "operational_metadata_only",
    }
    value.update(updates)
    return value


def store_path(workspace_root: Path) -> Path:
    return workspace_root / ".work-bundle" / "runtime" / "stage-events" / "events-v1.jsonl"


def test_api_004_validates_closed_typed_event_and_public_schema() -> None:
    validated = validate_stage_event(event())

    assert isinstance(validated, StageEventV1)
    assert validated.to_dict() == event()
    schema = json.loads(
        (REPO_ROOT / "references/assets/orchestration/contract/stage-event-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["$ref"] == "#/$defs/stageEvent"
    assert schema["$defs"]["stageEvent"]["additionalProperties"] is False
    assert set(schema["$defs"]["stageEvent"]["required"]) == set(event())
    assert set(schema["$defs"]["eventType"]["enum"]) == set(EVENT_TYPES)
    assert set(schema["$defs"]["findingClass"]["enum"]) == set(FINDING_CLASSES)


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_api_004_accepts_every_event_type(event_type: str) -> None:
    assert validate_stage_event(event(event_type=event_type)).event_type == event_type


@pytest.mark.parametrize("finding_class", FINDING_CLASSES)
def test_api_004_accepts_exact_finding_classes(finding_class: str) -> None:
    value = event(event_type="finding_recorded", finding_class=finding_class)
    assert validate_stage_event(value).finding_class == finding_class


def test_api_004_accepts_contract_valid_descriptive_operational_strings() -> None:
    value = event(
        stage="kernel convergence",
        owner="kernel convergence owner",
        return_reason="validation oracle unavailable",
    )

    validated = validate_stage_event(value)

    assert validated.stage == value["stage"]
    assert validated.owner == value["owner"]
    assert validated.return_reason == value["return_reason"]
    schema = json.loads(
        (REPO_ROOT / "references/assets/orchestration/contract/stage-event-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    properties = schema["$defs"]["stageEvent"]["properties"]
    assert properties["stage"] == {"type": "string", "minLength": 1}
    for field in ("owner", "return_reason"):
        assert {"type": "string", "minLength": 1} in properties[field]["anyOf"]


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda value: value.update(extra="no"), "WB_STAGE_EVENT_FIELDS_INVALID"),
        (lambda value: value["join_ids"].update(extra="no"), "WB_STAGE_EVENT_JOIN_IDS_INVALID"),
        (lambda value: value["clocks"].update(wall_ms=True), "WB_STAGE_EVENT_CLOCK_INVALID"),
        (lambda value: value["clocks"].update(active_ms=13), "WB_STAGE_EVENT_CLOCK_ORDER_INVALID"),
        (lambda value: value.update(enforcement_mode="advisory"), "WB_STAGE_EVENT_MODE_INVALID"),
        (lambda value: value.update(event_type=["stage_started"]), "WB_STAGE_EVENT_TYPE_INVALID"),
        (lambda value: value.update(timestamp="2026-09-05Z"), "WB_STAGE_EVENT_TIMESTAMP_INVALID"),
        (lambda value: value.update(finding_class="unknown"), "WB_STAGE_EVENT_FINDING_CLASS_INVALID"),
        (lambda value: value["identity"].update(mutation_epoch=-1), "WB_STAGE_EVENT_IDENTITY_INVALID"),
    ],
)
def test_api_004_rejects_open_or_invalid_contract_shapes(mutation, code: str) -> None:
    value = event()
    mutation(value)
    with pytest.raises(StageEventError, match=code):
        validate_stage_event(value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(prompt="private user content"),
        lambda value: value.update(owner="/Users/private/credentials.yaml"),
        lambda value: value.update(return_reason="diff --git a/secret b/secret"),
        lambda value: value.update(stage="Bearer synthetic-secret-value"),
        lambda value: value.update(owner="synthetic-secret-value"),
        lambda value: value["join_ids"].update(token="synthetic-secret-value"),
    ],
)
def test_api_004_privacy_filter_fails_closed_without_echoing_content(mutation) -> None:
    value = event()
    mutation(value)
    rendered = json.dumps(value)

    with pytest.raises(StageEventError) as caught:
        redact_event_payload(value)

    assert "synthetic-secret-value" not in str(caught.value)
    assert rendered not in str(caught.value)


def test_api_004_append_is_prefix_preserving_unique_and_monotonic(tmp_path: Path) -> None:
    first = append_stage_event(tmp_path, event())
    path = store_path(tmp_path)
    prefix = path.read_bytes()
    second_event = event(
        "event-002",
        timestamp="2026-09-05T01:02:03.100000Z",
        clocks={"wall_ms": 13, "active_ms": 9, "billed_ms": None},
    )
    second = append_stage_event(tmp_path, second_event)

    assert first.event_id == "event-001"
    assert second.event_id == "event-002"
    assert path.read_bytes().startswith(prefix)
    before_rejection = path.read_bytes()
    with pytest.raises(StageEventError, match="WB_STAGE_EVENT_DUPLICATE_ID"):
        append_stage_event(tmp_path, event())
    assert path.read_bytes() == before_rejection


def test_api_004_parses_timestamp_order_instead_of_comparing_text(tmp_path: Path) -> None:
    append_stage_event(tmp_path, event(timestamp="2026-09-05T01:02:03.9Z"))
    earlier = event(
        "event-002",
        timestamp="2026-09-05T01:02:03.10Z",
        clocks={"wall_ms": 13, "active_ms": 9, "billed_ms": None},
    )
    with pytest.raises(StageEventError, match="WB_STAGE_EVENT_TIMESTAMP_ORDER_INVALID"):
        append_stage_event(tmp_path, earlier)


def test_api_004_malformed_history_blocks_append_without_mutation(tmp_path: Path) -> None:
    path = store_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"event_id":"truncated"')
    before = path.read_bytes()

    with pytest.raises(StageEventError, match="WB_STAGE_EVENT_STORE_INVALID"):
        append_stage_event(tmp_path, event())

    assert path.read_bytes() == before


def test_api_004_semantically_nonmonotonic_history_is_invalid(tmp_path: Path) -> None:
    first = event(timestamp="2026-09-05T01:02:03.9Z", clocks={"wall_ms": 14, "active_ms": 9, "billed_ms": None})
    second = event(
        "event-002",
        timestamp="2026-09-05T01:02:03.10Z",
        clocks={"wall_ms": 13, "active_ms": 9, "billed_ms": None},
    )
    path = store_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(json.dumps(item) for item in (first, second)) + "\n", encoding="utf-8")

    with pytest.raises(StageEventError, match="WB_STAGE_EVENT_STORE_INVALID"):
        query_stage_events(tmp_path)


def test_api_004_query_and_export_preserve_order_and_do_not_mutate(tmp_path: Path) -> None:
    append_stage_event(tmp_path, event())
    append_stage_event(
        tmp_path,
        event(
            "event-002",
            process_id="process-002",
            attempt_id="attempt-002",
            event_type="suite_started",
            enforcement_mode="native",
        ),
    )
    before = store_path(tmp_path).read_bytes()

    assert [item.event_id for item in query_stage_events(tmp_path)] == ["event-001", "event-002"]
    assert [item.event_id for item in query_stage_events(tmp_path, process_id="process-002")] == ["event-002"]
    assert export_stage_events(tmp_path).encode() == before
    assert store_path(tmp_path).read_bytes() == before


def test_api_004_rejects_symlinked_store_boundary(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    runtime = tmp_path / ".work-bundle" / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "stage-events").symlink_to(outside, target_is_directory=True)

    with pytest.raises(StageEventError, match="WB_STAGE_EVENT_STORE_BOUNDARY_INVALID"):
        append_stage_event(tmp_path, event())
    assert not (outside / "events-v1.jsonl").exists()


def test_dispatcher_exposes_stage_event_append_query_and_export(tmp_path: Path) -> None:
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event()), encoding="utf-8")
    commands = [
        ("stage-event-append", ["--workspace-root", str(tmp_path), "--event-file", str(event_file)]),
        ("stage-event-query", ["--workspace-root", str(tmp_path), "--process-id", "process-001"]),
        ("stage-event-export", ["--workspace-root", str(tmp_path)]),
    ]

    results = [
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "wb.py"), command, *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        for command, args in commands
    ]

    assert [result.returncode for result in results] == [0, 0, 0]
    assert json.loads(results[0].stdout)["event_id"] == "event-001"
    assert json.loads(results[1].stdout)[0]["process_id"] == "process-001"
    assert json.loads(results[2].stdout.splitlines()[0])["event_id"] == "event-001"
