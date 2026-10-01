from __future__ import annotations

import copy
import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "keep-summarizing"


@pytest.fixture
def modules():
    names = ("core", "indexes", "transactions", "notes", "questions", "dispatcher")
    previous = {name: sys.modules.pop(name, None) for name in names}
    sys.path.insert(0, str(SCRIPTS))
    try:
        yield {name: importlib.import_module(name) for name in names}
    finally:
        sys.path.remove(str(SCRIPTS))
        for name in names:
            sys.modules.pop(name, None)
            if previous[name] is not None:
                sys.modules[name] = previous[name]


REGISTRY_OPTION_ROUTES = [
    ["resolve"],
    ["mutate-knowledge", "--project", "fixture", "--request-file", "request.yaml"],
    ["register-project", "--project", "fixture", "--project-root", "/fixture"],
    ["unregister-project", "--project", "fixture"],
    ["list-projects"],
    ["registry-doctor"],
]


@pytest.mark.parametrize("argv", REGISTRY_OPTION_ROUTES)
def test_current_parser_rejects_ignored_registry_override_without_dispatch(modules, argv, capsys):
    with pytest.raises(SystemExit) as error:
        modules["dispatcher"].build_parser().parse_args(argv + ["--registry-file", "/unused-registry.yaml"])
    assert error.value.code == 2
    assert "unrecognized arguments: --registry-file" in capsys.readouterr().err


@pytest.mark.parametrize("argv", REGISTRY_OPTION_ROUTES)
def test_current_help_does_not_advertise_ignored_registry_override(modules, argv, capsys):
    with pytest.raises(SystemExit) as error:
        modules["dispatcher"].build_parser().parse_args([argv[0], "--help"])
    assert error.value.code == 0
    assert "--registry-file" not in capsys.readouterr().out


def test_registry_option_removal_preserves_explicit_resolution_and_registration_inputs(modules):
    parser = modules["dispatcher"].build_parser()
    args = parser.parse_args([
        "resolve", "--project-root", "/fixture", "--knowledge-root", "/knowledge", "--cwd", "/context",
    ])
    assert (args.project_root, args.knowledge_root, args.cwd) == ("/fixture", "/knowledge", "/context")
    registered = parser.parse_args([
        "register-project", "--project", "fixture", "--project-root", "/fixture",
        "--name", "Fixture", "--alias", "alias", "--source", "/source",
    ])
    assert (registered.project, registered.project_root, registered.name) == ("fixture", "/fixture", "Fixture")
    assert registered.alias == ["alias"] and registered.source == ["/source"]


def note_request(title="Example", status="draft"):
    return {
        "effect": "create", "kind": "note",
        "path": f"notes/development-design/architecture/decisions/{title.lower()}.md",
        "expected_digest": None,
        "record": {
            "id": f"note-{title.lower()}", "title": title,
            "lifecycle_stage": "development_design",
            "perspective": "development-design/architecture/decisions",
            "status": status, "source_type": "design_doc", "summary": "A point.",
            "owner": "keep-summarizing", "created_at": "2026-09-29",
            "updated_at": "2026-09-29", "visibility": "private", "sensitivity": "normal",
            "tags": [], "evidence": [], "related_notes": [], "supersedes": [],
            "superseded_by": [], "embedding": {"include": True, "chunk_strategy": "heading"},
        },
        "body": "# Example\n\nSemantically poor but structurally valid prose.\n",
    }


def write_existing(root, request, *, newline=None):
    path = root / request["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.safe_dump(request["record"], sort_keys=False) + "---\n\n" + request["body"], newline=newline)
    return path


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_dry_run_validates_without_any_filesystem_effect(modules, tmp_path):
    root = tmp_path / "absent"
    result = modules["transactions"].mutate_record(root, "fixture", note_request(), dry_run=True)
    assert result["canonical_status"] == "unchanged"
    assert result["projection_status"] == "not-run"
    assert not root.exists()


@pytest.mark.parametrize("defect,code", [("digest", "KS_STALE_DIGEST"), ("transition", "KS_INVALID_TRANSITION")])
def test_rejections_have_zero_prewrite_effect(modules, tmp_path, defect, code):
    request = note_request()
    path = write_existing(tmp_path, request)
    request["effect"] = "update"
    request["expected_digest"] = digest(path)
    if defect == "digest":
        request["expected_digest"] = "sha256:" + "0" * 64
    else:
        request["record"]["status"] = "current"
    before = snapshot(tmp_path)
    with pytest.raises(modules["transactions"].KnowledgeError) as error:
        modules["transactions"].mutate_record(tmp_path, "fixture", request)
    assert error.value.code == code
    assert snapshot(tmp_path) == before


def test_projection_failure_keeps_replaced_canonical_authority(modules, tmp_path, monkeypatch):
    request = note_request()
    path = write_existing(tmp_path, request)
    request.update(effect="update", expected_digest=digest(path), body="# Example\n\nChanged.\n")
    def fail(*_args):
        raise OSError("injected projection failure")
    monkeypatch.setattr(modules["transactions"], "rebuild_projections", fail)
    result = modules["transactions"].mutate_record(tmp_path, "fixture", request)
    assert result["canonical_status"] == "replaced"
    assert result["projection_status"] == "stale"
    assert result["code"] == "KS_PROJECTION_STALE"
    assert result["rebuild_command"][:3] == ["scripts/ks.py", "index", "--project"]
    record, body = modules["core"].read_front_matter(path)
    assert body.strip() == "# Example\n\nChanged."
    assert record["embedding"] == request["record"]["embedding"]
    assert result["digest"] == digest(path)


@pytest.fixture
def local_projections(modules, monkeypatch):
    # The production FTS/document/question builders run; vector backend behavior
    # has independent real-runtime coverage in test_keep_summarizing_query.py.
    monkeypatch.setattr(modules["indexes"], "build_vector_index_status", lambda *_args: {"status": "rebuilt"})
    return modules["transactions"]


def question_request():
    return {
        "effect": "create", "kind": "open-question",
        "path": "open-questions/development-design/architecture/decisions/example.md",
        "expected_digest": None,
        "record": {
            "id": "oq-example", "title": "Example Question",
            "perspective": "development-design/architecture/decisions", "status": "open",
            "created_at": "2026-09-29", "updated_at": "2026-09-29",
            "source_note_ids": [], "trigger_terms": ["an example"],
            "resolved_at": None, "resolved_by_note_id": None, "resolution_summary": None,
        },
        "body": "# Example Question\n\n## Question\n\nWhat happens?\n",
    }


@pytest.mark.parametrize("effect", ["create", "update", "resolve-open-question"])
@pytest.mark.parametrize("trigger_terms", [[], [""], ["   "], [1]])
def test_question_trigger_terms_rejection_preserves_canonical_and_projections(
    modules, local_projections, tmp_path, effect, trigger_terms
):
    existing = question_request()
    local_projections.mutate_record(tmp_path, "fixture", existing)
    request = copy.deepcopy(existing)
    request["effect"] = effect
    if effect == "create":
        request["path"] = request["path"].replace("example.md", "new-question.md")
        request["record"]["id"] = "oq-new-question"
    else:
        request["expected_digest"] = digest(tmp_path / existing["path"])
        request["body"] = "The proposed replacement body.\n"
        if effect == "resolve-open-question":
            request["record"].update(
                status="resolved", resolved_at="2026-09-30", resolution_summary="Declared answer."
            )
    request["record"]["trigger_terms"] = trigger_terms
    before = snapshot(tmp_path)
    before_filesystem = {
        str(path.relative_to(tmp_path)): path.stat().st_mtime_ns
        for path in tmp_path.rglob("*")
    }

    with pytest.raises(modules["transactions"].KnowledgeError) as error:
        local_projections.mutate_record(tmp_path, "fixture", request)

    assert error.value.code == "KS_INVALID_RECORD"
    assert "trigger_terms" in str(error.value)
    assert snapshot(tmp_path) == before
    assert {
        str(path.relative_to(tmp_path)): path.stat().st_mtime_ns
        for path in tmp_path.rglob("*")
    } == before_filesystem


def test_create_then_update_stages_one_sibling_and_rebuilds_existing_projections(modules, local_projections, tmp_path, monkeypatch):
    request = note_request()
    original_replace = modules["transactions"].os.replace
    replaced = []
    def replace(source, target):
        assert Path(source).parent == Path(target).parent
        assert Path(source) != Path(target)
        fm, body = modules["core"].read_front_matter(Path(source))
        assert fm == request["record"]
        assert body == request["body"]
        replaced.append(Path(target))
        original_replace(source, target)
    monkeypatch.setattr(modules["transactions"].os, "replace", replace)
    result = local_projections.mutate_record(tmp_path, "fixture", request)
    path = tmp_path / request["path"]
    assert replaced == [path]
    assert result["projection_status"] == "rebuilt"
    assert result["projections"]["counts"]["documents"] == 1
    assert (tmp_path / "indexes" / "knowledge.sqlite").exists()
    rows = [json.loads(line) for line in (tmp_path / "indexes" / "document-registry.jsonl").read_text().splitlines()]
    assert rows[0]["status"] == "draft"
    request.update(effect="update", expected_digest=digest(path), body="# Updated\n\nChanged.\n")
    result = local_projections.mutate_record(tmp_path, "fixture", request)
    assert len(replaced) == 2
    assert modules["core"].read_front_matter(path) == (request["record"], request["body"])
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("effect,status", [("transition", "confirmed"), ("supersede", "superseded"), ("deprecate", "deprecated")])
def test_note_lifecycle_effect_replaces_only_named_record(modules, local_projections, tmp_path, effect, status):
    request = note_request()
    path = write_existing(tmp_path, request)
    replacement = note_request("Replacement", "current")
    replacement_path = write_existing(tmp_path, replacement)
    replacement_bytes = replacement_path.read_bytes()
    request.update(effect=effect, expected_digest=digest(path))
    request["record"]["status"] = status
    request["record"]["evidence"] = [{"type": "source_note", "path": replacement["path"], "relation": "confirms"}]
    if effect != "transition":
        request["record"]["superseded_by"] = [replacement["record"]["id"]]
    result = local_projections.mutate_record(tmp_path, "fixture", request)
    assert result["status"] == status
    assert replacement_path.read_bytes() == replacement_bytes
    assert modules["core"].read_front_matter(path)[0]["evidence"] == request["record"]["evidence"]


def test_question_resolves_from_canonical_without_registry_or_note_mutation(modules, local_projections, tmp_path):
    note = note_request()
    note_path = write_existing(tmp_path, note)
    before_note = note_path.read_bytes()
    question = question_request()
    question["record"]["source_note_ids"] = [note["record"]["id"]]
    result = local_projections.mutate_record(tmp_path, "fixture", question)
    path = tmp_path / question["path"]
    (tmp_path / "indexes" / "open-question-registry.jsonl").unlink()
    question.update(effect="resolve-open-question", expected_digest=digest(path), body="# Example\n\nThe declared answer.\n")
    question["record"].update(status="resolved", resolved_at="2026-09-30", resolved_by_note_id=note["record"]["id"], resolution_summary="The declared answer.")
    result = local_projections.mutate_record(tmp_path, "fixture", question)
    assert result["old_status"] == "open" and result["status"] == "resolved"
    assert note_path.read_bytes() == before_note
    assert modules["core"].read_front_matter(path)[0]["source_note_ids"] == [note["record"]["id"]]
    assert json.loads((tmp_path / "indexes" / "open-question-registry.jsonl").read_text())["status"] == "resolved"


@pytest.mark.parametrize("defect,code", [
    ("path-collision", "KS_COLLISION"), ("id-collision", "KS_COLLISION"),
    ("bad-path", "KS_INVALID_PATH"), ("perspective", "KS_INVALID_RECORD"),
    ("evidence", "KS_INVALID_LINK"), ("link", "KS_INVALID_LINK"),
    ("markdown", "KS_INVALID_LINK"), ("escape", "KS_INVALID_LINK"),
    ("missing-field", "KS_INVALID_RECORD"), ("reasoning", "KS_INVALID_REQUEST"),
    ("source-reasoning", "KS_INVALID_RECORD"),
])
def test_invalid_create_refuses_before_mutation(modules, tmp_path, defect, code):
    request = note_request()
    if defect == "path-collision":
        write_existing(tmp_path, request)
    elif defect == "id-collision":
        other = copy.deepcopy(request)
        other["path"] = other["path"].replace("example.md", "duplicate.md")
        write_existing(tmp_path, other)
    elif defect == "bad-path":
        request["path"] = "../escaped.md"
    elif defect == "perspective":
        request["record"]["lifecycle_stage"] = "implementation"
    elif defect == "evidence":
        request["record"]["evidence"] = [{"type": "source_code", "path": "missing.py", "relation": "implements"}]
    elif defect == "link":
        request["record"]["related_notes"] = ["missing-id"]
    elif defect == "markdown":
        request["body"] += "[Missing](missing.md)"
    elif defect == "escape":
        request["body"] += "[Escapes](../../../../../../missing.md)"
    elif defect == "missing-field":
        del request["record"]["embedding"]
    elif defect == "reasoning":
        request["materiality_reasoning"] = "Not an effect input"
    elif defect == "source-reasoning":
        request["record"]["source"] = {"sufficiency_analysis": "Not contract metadata"}
    before = snapshot(tmp_path)
    with pytest.raises(modules["transactions"].KnowledgeError) as error:
        modules["transactions"].mutate_record(tmp_path, "fixture", request)
    assert error.value.code == code
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("effect,target", [("transition", "superseded"), ("transition", "deprecated"), ("resolve-open-question", "resolved")])
def test_reserved_effects_cannot_be_bypassed(modules, tmp_path, effect, target):
    request = note_request()
    path = write_existing(tmp_path, request)
    request.update(effect=effect, expected_digest=digest(path))
    request["record"]["status"] = target
    before = snapshot(tmp_path)
    with pytest.raises(modules["transactions"].KnowledgeError):
        modules["transactions"].mutate_record(tmp_path, "fixture", request)
    assert snapshot(tmp_path) == before


def test_promotion_requires_evidence_and_replacement_requires_existing_link(modules, tmp_path):
    request = note_request()
    path = write_existing(tmp_path, request)
    request.update(effect="transition", expected_digest=digest(path))
    request["record"]["status"] = "current"
    with pytest.raises(modules["transactions"].KnowledgeError, match="promotion requires"):
        modules["transactions"].mutate_record(tmp_path, "fixture", request)
    request["effect"] = "supersede"
    request["record"]["status"] = "superseded"
    with pytest.raises(modules["transactions"].KnowledgeError, match="replacement reference"):
        modules["transactions"].mutate_record(tmp_path, "fixture", request)


def test_atomic_replace_failure_preserves_canonical_bytes(modules, tmp_path, monkeypatch):
    request = note_request()
    path = write_existing(tmp_path, request)
    before = snapshot(tmp_path)
    request.update(effect="update", expected_digest=digest(path), body="Changed.")
    def fail(*_args):
        raise OSError("injected replace failure")
    monkeypatch.setattr(modules["transactions"].os, "replace", fail)
    with pytest.raises(modules["transactions"].KnowledgeError) as error:
        modules["transactions"].mutate_record(tmp_path, "fixture", request)
    assert error.value.code == "KS_WRITE_FAILED"
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("command", ["mutate-knowledge", "write-note", "add-question", "resolve-question"])
def test_public_routes_use_declared_request_owner(modules, tmp_path, capsys, command):
    request = note_request() if command in {"mutate-knowledge", "write-note"} else question_request()
    if command == "resolve-question":
        path = write_existing(tmp_path, request)
        request.update(effect="resolve-open-question", expected_digest=digest(path))
        request["record"].update(status="resolved", resolved_at="2026-09-30", resolution_summary="Declared answer.")
    request_file = tmp_path / "request.yaml"
    request_file.write_text(yaml.safe_dump(request, sort_keys=False))
    before = snapshot(tmp_path)
    args = modules["dispatcher"].build_parser().parse_args([command, "--project", "fixture", "--knowledge-root", str(tmp_path), "--request-file", str(request_file), "--dry-run"])
    args.func(args)
    result = json.loads(capsys.readouterr().out)
    assert result["canonical_status"] == "unchanged"
    assert result["dry_run"] is True
    assert snapshot(tmp_path) == before


def test_public_route_reports_typed_prewrite_failure(modules, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"effect": "create", "materiality": "unused"}))
    args = modules["dispatcher"].build_parser().parse_args(["mutate-knowledge", "--project", "fixture", "--knowledge-root", str(tmp_path), "--request-file", str(request_file)])
    with pytest.raises(SystemExit) as error:
        args.func(args)
    assert error.value.code == 2
    result = json.loads(capsys.readouterr().out)
    assert result["code"] == "KS_INVALID_REQUEST"
    assert result["canonical_status"] == "unchanged"


def test_nested_front_matter_preserves_quotes_dates_evidence_and_embedding(modules, tmp_path):
    path = tmp_path / "note.md"
    path.write_text('---\nid: example\ntitle: "Quoted: title"\nupdated_at: 2026-09-29\nevidence:\n  - type: specification\n    path: spec.md\n    relation: confirms\nembedding:\n  include: false\n  chunk_strategy: heading\n---\nBody\n')
    fm, body = modules["core"].read_front_matter(path)
    assert fm["title"] == "Quoted: title"
    assert fm["updated_at"] == "2026-09-29"
    assert fm["evidence"] == [{"type": "specification", "path": "spec.md", "relation": "confirms"}]
    assert fm["embedding"] == {"include": False, "chunk_strategy": "heading"}
    assert body == "Body\n"


@pytest.mark.parametrize("key,value", [("kind", []), ("effect", []), ("record", []), ("body", []), ("path", [])])
def test_wrong_request_types_have_typed_failure(modules, tmp_path, key, value):
    request = note_request()
    request[key] = value
    with pytest.raises(modules["transactions"].KnowledgeError):
        modules["transactions"].mutate_record(tmp_path, "fixture", request, dry_run=True)
    assert snapshot(tmp_path) == {}


@pytest.mark.parametrize("defect", ["digest-race", "staged-invalid"])
def test_staging_rechecks_digest_and_render_before_replace(modules, tmp_path, monkeypatch, defect):
    request = note_request()
    path = write_existing(tmp_path, request)
    original_bytes = path.read_bytes()
    request.update(effect="update", expected_digest=digest(path), body="Declared change.\n")
    original_reader = modules["transactions"].read_front_matter
    def read_staged(staged):
        value = original_reader(staged)
        if defect == "digest-race":
            path.write_bytes(original_bytes + b"external edit\n")
        else:
            return {}, "invalid staged body"
        return value
    monkeypatch.setattr(modules["transactions"], "read_front_matter", read_staged)
    with pytest.raises(modules["transactions"].KnowledgeError):
        modules["transactions"].mutate_record(tmp_path, "fixture", request)
    assert "Declared change." not in path.read_text()
    assert path.read_bytes() == (original_bytes + b"external edit\n" if defect == "digest-race" else original_bytes)
    assert not list(path.parent.glob("*.tmp"))


def test_unavailable_vector_projection_is_reported_as_regenerable_after_write(modules, tmp_path, monkeypatch):
    request = note_request()
    monkeypatch.setattr(modules["indexes"], "build_vector_index_status", lambda *_args: {"status": "unavailable", "reason": "fixture backend unavailable"})
    result = modules["transactions"].mutate_record(tmp_path, "fixture", request)
    assert result["canonical_status"] == "replaced"
    assert result["projection_status"] == "stale"
    assert result["projections"]["index_status"]["sqlite_fts"] == "rebuilt"
    assert result["projection_error"] == "fixture backend unavailable"
    assert (tmp_path / request["path"]).exists()


def test_public_route_reports_post_replacement_failure_without_rollback(modules, tmp_path, capsys, monkeypatch):
    request = note_request()
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(request))
    def fail(*_args):
        raise OSError("fixture index failure")
    monkeypatch.setattr(modules["transactions"], "rebuild_projections", fail)
    args = modules["dispatcher"].build_parser().parse_args(["write-note", "--project", "fixture", "--knowledge-root", str(tmp_path), "--request-file", str(request_file)])
    with pytest.raises(SystemExit) as error:
        args.func(args)
    result = json.loads(capsys.readouterr().out)
    assert error.value.code == 1
    assert result["code"] == "KS_PROJECTION_STALE"
    assert result["canonical_status"] == "replaced"
    assert modules["core"].read_front_matter(tmp_path / request["path"]) == (request["record"], request["body"])


def test_real_projection_case_checks_runtime_before_mutation(modules, tmp_path, monkeypatch):
    monkeypatch.setattr(modules["indexes"], "sqlite_vec_availability_probe", lambda: {
        "status": "unavailable", "reason": "fixture SQLite extension unavailable",
    })
    monkeypatch.setattr(modules["transactions"], "mutate_record", lambda *_args: pytest.fail(
        "unavailable integration runtime must be detected before mutation"
    ))
    with pytest.raises(pytest.skip.Exception, match="fixture SQLite extension unavailable"):
        test_normal_transaction_uses_real_managed_projection_runtime(modules, tmp_path)
    assert not (tmp_path / "notes").exists()


def test_normal_transaction_uses_real_managed_projection_runtime(modules, tmp_path):
    # Probe the interpreter's extension capability independently, as the query
    # integration tests do. Never turn a production rebuild failure into a skip.
    probe = modules["indexes"].sqlite_vec_availability_probe()
    if probe["status"] == "unavailable":
        pytest.skip(str(probe["reason"]))
    assert probe == {"status": "available", "reason": None}
    request = note_request()
    result = modules["transactions"].mutate_record(tmp_path, "fixture", request)
    assert result["canonical_status"] == "replaced"
    assert result["projection_status"] == "rebuilt", result
    assert result["projections"]["vector_status"]["chunks_indexed"] == 1
    assert (tmp_path / "indexes" / "vector-index.jsonl").read_text()


@pytest.mark.parametrize("initial_newline", ["\n", "\r\n"])
def test_existing_crlf_canonical_is_digest_bound_and_replaced_losslessly(modules, local_projections, tmp_path, initial_newline):
    request = note_request()
    path = write_existing(tmp_path, request, newline=initial_newline)
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert b"\r\r\n" not in path.read_bytes()
    assert b"\r\n" in path.read_bytes()
    request.update(effect="update", expected_digest=digest(path), body="The supplied body.\n")
    result = local_projections.mutate_record(tmp_path, "fixture", request)
    assert result["digest"] == digest(path)
    assert modules["core"].read_front_matter(path) == (request["record"], request["body"])
