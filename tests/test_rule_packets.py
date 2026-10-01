from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/work-bundle"))


@pytest.fixture
def stores(tmp_path, monkeypatch):
    import rules

    workspace = tmp_path / "workspace"
    (workspace / ".work-bundle").mkdir(parents=True)
    (workspace / ".work-bundle/project.yaml").write_text("metadata_version: 4\nauthority: canonical\nworkspace:\n  id: fixture-workspace\n")
    roots = {scope: tmp_path / scope / "rules" for scope in ("toolkit", "global", "project")}
    for scope, root in roots.items():
        root.mkdir(parents=True)
        entry = {"id": scope, "path": f"{scope}.md", "applies_when": ["agent supplied signal"],
                 "enforcement": "must", "load": "conditional", "requires": []}
        (root / entry["path"]).write_text("---\n" + yaml.safe_dump({k: v for k, v in entry.items() if k != "path"}) + "---\nBody.\n")
        (root / "index.yaml").write_text(yaml.safe_dump({"rules": [entry]}))
    monkeypatch.setattr(rules, "rule_store_sources", lambda _: [
        {"scope": scope, "rules_root": root, "index_path": root / "index.yaml", "required": scope == "toolkit"}
        for scope, root in roots.items()
    ])
    return workspace, roots


def binding(workspace):
    return {"workspace_root": str(workspace), "packet_id": "plan-20260929-001/task-006/task-brief", "lifecycle_stage": "implementation",
            "observable_signals": {"operation": ["edit"], "file_scope": ["scripts"]}}


def loaded(roots, *ids):
    return {id_: hashlib.sha256((roots[id_] / f"{id_}.md").read_bytes()).hexdigest() for id_ in ids}


def capture(stores, ids=("toolkit",)):
    import rule_packet
    workspace, roots = stores
    return rule_packet.capture_packet(workspace, "selected", binding(workspace), loaded(roots, *ids))


def inspect(stores, **changes):
    import rule_packet
    workspace, _ = stores
    current = binding(workspace)
    current.update(changes)
    return rule_packet.inspect_packet(workspace, "selected", current)


def test_capture_hit_delete_and_regenerate(stores):
    import rule_packet
    workspace, _ = stores
    assert inspect(stores)["status"] == "miss"
    result = capture(stores)
    path = Path(result["packet_path"])
    assert path == workspace / ".work-bundle/runtime/rule-packets/selected.json"
    packet = json.loads(path.read_text())
    assert packet["disposable"] is True
    assert packet["schema_version"] == 1
    assert set(packet["context_binding"]) == {"workspace_id", "controller_or_task_packet_id", "lifecycle_stage", "operation_signal_digest"}
    assert packet["context_binding"]["workspace_id"] == "fixture-workspace"
    assert packet["created_at"].endswith("Z")
    assert packet["selected_rules"] == [{"id": "toolkit", "scope": "toolkit", "path": "toolkit.md",
        "index_entry_digest": packet["comparison"]["selected_bodies"]["toolkit"]["index_entry_digest"],
        "body_digest": loaded(stores[1], "toolkit")["toolkit"], "dependency_ids": []}]
    assert packet["comparison"]["selected_bodies"]["toolkit"]["body"] == "---\napplies_when:\n- agent supplied signal\nenforcement: must\nid: toolkit\nload: conditional\nrequires: []\n---\nBody.\n"
    hit = inspect(stores)
    assert hit["status"] == "hit"
    assert hit["reusable_selected_ids"] == ["toolkit"]
    assert hit["requires_agent_reassessment"] is False
    path.unlink()
    assert inspect(stores)["status"] == "miss"
    assert capture(stores)["status"] == "captured"
    with pytest.raises(ValueError, match="packet_name"):
        rule_packet.capture_packet(workspace, "../../authority", binding(workspace), {})


@pytest.mark.parametrize("change", ["added", "changed", "removed", "formatting"])
def test_every_unselected_index_delta_requires_agent_reassessment(stores, change):
    _, roots = stores
    capture(stores)
    path = roots["global"] / "index.yaml"
    data = yaml.safe_load(path.read_text())
    if change == "added":
        entry = dict(data["rules"][0], id="new", path="new.md")
        data["rules"].append(entry)
    elif change == "changed":
        data["rules"][0]["applies_when"] = ["new adjacent operation"]
    elif change == "removed":
        data["rules"] = []
    if change == "formatting":
        path.write_text(path.read_text() + "# formatting changed\n")
    else:
        path.write_text(yaml.safe_dump(data))
    result = inspect(stores)
    assert result["status"] == "refresh-required"
    assert result["requires_agent_reassessment"] is True
    assert result["reusable_selected_ids"] == ["toolkit"]
    assert result["index_deltas"]["indexes_changed"] == ["global"]
    assert result["index_deltas"][change] if change != "formatting" else not result["index_deltas"]["changed"]
    assert "new" not in result["reusable_selected_ids"]


@pytest.mark.parametrize("field,value", [("packet_id", "another-task"), ("lifecycle_stage", "review"),
    ("observable_signals", {"operation": ["read"]})])
def test_context_changes_preclude_reuse(stores, field, value):
    capture(stores)
    result = inspect(stores, **{field: value})
    assert result["requires_agent_reassessment"] is True
    assert result["reusable_selected_ids"] == []


def test_changed_body_and_missing_selected_body(stores):
    _, roots = stores
    capture(stores)
    path = roots["toolkit"] / "toolkit.md"
    path.write_text(path.read_text() + "Changed body.\n")
    result = inspect(stores)
    assert result["reload_selected_ids"] == ["toolkit"]
    assert result["reusable_selected_ids"] == []
    path.unlink()
    assert inspect(stores)["status"] == "blocked"


def test_dependencies_must_be_explicitly_loaded_and_exactly_bound(stores):
    import rule_packet
    workspace, roots = stores
    index = roots["toolkit"] / "index.yaml"
    data = yaml.safe_load(index.read_text())
    data["rules"][0]["requires"] = ["global"]
    index.write_text(yaml.safe_dump(data))
    body = roots["toolkit"] / "toolkit.md"
    body.write_text(body.read_text().replace("requires: []", "requires: [global]"))
    with pytest.raises(ValueError, match="selected_dependency_missing:toolkit:global"):
        capture(stores)
    capture(stores, ("toolkit", "global"))
    (roots["global"] / "global.md").write_text((roots["global"] / "global.md").read_text() + "Changed.\n")
    result = inspect(stores)
    assert result["reload_selected_ids"] == ["global", "toolkit"]
    with pytest.raises(ValueError, match="loaded_digest_mismatch"):
        rule_packet.capture_packet(workspace, "selected", binding(workspace), {"toolkit": "0" * 64, **loaded(roots, "global")})


def test_corrupt_packet_is_disposable_miss_and_never_selection_authority(stores):
    path = Path(capture(stores)["packet_path"])
    path.write_text("not JSON")
    assert inspect(stores)["status"] == "miss"
    capture(stores)
    data = json.loads(path.read_text())
    data["comparison"]["selected_bodies"]["toolkit"]["body"] = "tampered"
    path.write_text(json.dumps(data))
    assert inspect(stores)["status"] == "miss"


def test_removed_selected_entry_reports_delta_for_agent_reassessment(stores):
    _, roots = stores
    capture(stores)
    (roots["toolkit"] / "index.yaml").write_text("rules: []\n")
    result = inspect(stores)
    assert result["status"] == "refresh-required"
    assert result["index_deltas"]["removed"] == ["toolkit"]
    assert result["reload_selected_ids"] == ["toolkit"]
    assert result["requires_agent_reassessment"] is True
    assert result["reusable_selected_ids"] == []


def test_crlf_bytes_can_be_loaded_and_byte_change_invalidates_reuse(stores):
    _, roots = stores
    path = roots["toolkit"] / "toolkit.md"
    text = path.read_text()
    path.write_bytes(text.replace("\n", "\r\n").encode())
    capture(stores)
    assert inspect(stores)["status"] == "hit"
    path.write_bytes(text.encode())
    assert inspect(stores)["reload_selected_ids"] == ["toolkit"]


def test_runtime_must_be_ignored_before_capture_and_reuse(stores):
    import rule_packet
    workspace, _ = stores
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    with pytest.raises(ValueError, match="untracked_and_ignored"):
        capture(stores)
    assert not (workspace / ".work-bundle/runtime").exists()
    (workspace / ".gitignore").write_text(".work-bundle/runtime/\n")
    capture(stores)
    assert inspect(stores)["status"] == "hit"
    (workspace / ".gitignore").unlink()
    assert inspect(stores)["status"] == "blocked"


def test_invalid_registry_blocks_packet_with_deltas_and_no_mutation(stores):
    _, roots = stores
    path = Path(capture(stores)["packet_path"])
    before = path.read_bytes()
    index = roots["global"] / "index.yaml"
    data = yaml.safe_load(index.read_text())
    data["rules"][0]["requires"] = ["missing"]
    index.write_text(yaml.safe_dump(data))
    result = inspect(stores)
    assert result["status"] == "blocked"
    assert result["requires_agent_reassessment"] is True
    assert "missing_required_rule:global:missing" in result["failures"][0]
    assert path.read_bytes() == before


def test_optional_scope_add_remove_and_packet_regeneration(stores):
    _, roots = stores
    index = roots["global"] / "index.yaml"
    content = index.read_text()
    index.unlink()
    capture(stores)
    index.write_text(content)
    result = inspect(stores)
    assert result["index_deltas"]["added"] == ["global"]
    assert result["requires_agent_reassessment"] is True
    # The caller supplies the same selected IDs after reassessment.
    capture(stores)
    assert inspect(stores)["status"] == "hit"
    index.unlink()
    assert inspect(stores)["index_deltas"]["removed"] == ["global"]


def test_entry_scope_and_path_changes_invalidate_selected_reuse(stores):
    _, roots = stores
    capture(stores)
    source_index = roots["toolkit"] / "index.yaml"
    entry = yaml.safe_load(source_index.read_text())["rules"][0]
    source_index.write_text("rules: []\n")
    target_index = roots["project"] / "index.yaml"
    data = yaml.safe_load(target_index.read_text())
    entry["path"] = "moved.md"
    data["rules"].append(entry)
    target_index.write_text(yaml.safe_dump(data))
    (roots["project"] / "moved.md").write_bytes((roots["toolkit"] / "toolkit.md").read_bytes())
    result = inspect(stores)
    assert result["index_deltas"]["changed"] == ["toolkit"]
    assert result["reload_selected_ids"] == ["toolkit"]
    assert result["reusable_selected_ids"] == []


def test_always_manual_and_transitive_dependency_selection_remain_explicit(stores):
    _, roots = stores
    for scope, load, requires in (("toolkit", "always", ["global"]), ("global", "manual", ["project"]),
                                 ("project", "conditional", [])):
        index = roots[scope] / "index.yaml"
        data = yaml.safe_load(index.read_text())
        data["rules"][0].update(load=load, requires=requires)
        index.write_text(yaml.safe_dump(data))
        (roots[scope] / f"{scope}.md").write_text("---\n" + yaml.safe_dump({key: value for key, value in data["rules"][0].items() if key != "path"}) + "---\nBody.\n")
    with pytest.raises(ValueError, match="always_rule_not_loaded:toolkit"):
        capture(stores, ())
    with pytest.raises(ValueError, match="selected_dependency_missing:global:project"):
        capture(stores, ("toolkit", "global"))
    result = capture(stores, ("toolkit", "global", "project"))
    packet = json.loads(Path(result["packet_path"]).read_text())
    assert set(packet["comparison"]["selected_bodies"]["toolkit"]["dependencies"]) == {"global", "project"}
    body = roots["project"] / "project.md"
    body.write_text(body.read_text() + "New dependency body.\n")
    assert inspect(stores)["reload_selected_ids"] == ["global", "project", "toolkit"]


def test_duplicate_and_cycle_indexes_block_before_packet_write(stores):
    _, roots = stores
    index = roots["global"] / "index.yaml"
    original = yaml.safe_load(index.read_text())
    duplicate = {"rules": [dict(original["rules"][0], id="toolkit")]}
    index.write_text(yaml.safe_dump(duplicate))
    with pytest.raises(ValueError, match="duplicate_rule_id:toolkit"):
        capture(stores)
    original["rules"][0]["requires"] = ["global"]
    index.write_text(yaml.safe_dump(original))
    with pytest.raises(ValueError, match="dependency_cycle:global->global"):
        capture(stores)
    workspace, _ = stores
    assert not (workspace / ".work-bundle/runtime").exists()


def test_cli_public_route_uses_explicit_loaded_ids(tmp_path):
    toolkit = tmp_path / "toolkit"
    root = toolkit / "rules"
    root.mkdir(parents=True)
    entry = {"id": "selected", "path": "selected.md", "applies_when": ["source edit"], "load": "conditional",
             "enforcement": "must", "requires": []}
    body = "---\n" + yaml.safe_dump({key: value for key, value in entry.items() if key != "path"}) + "---\nBody.\n"
    (root / "selected.md").write_text(body)
    (root / "index.yaml").write_text(yaml.safe_dump({"rules": [entry]}))
    workspace = tmp_path / "workspace"
    (workspace / ".work-bundle").mkdir(parents=True)
    (workspace / ".work-bundle/project.yaml").write_text("metadata_version: 4\nauthority: canonical\nworkspace:\n  id: cli-workspace\n")
    config = tmp_path / "home/.work-bundle"
    config.mkdir(parents=True)
    (config / "bootstrap.yaml").write_text(f"bootstrap_version: v1\nwork_bundle_root: {toolkit}\n")
    import os
    env = dict(os.environ, WB_WORK_BUNDLE_ROOT=str(toolkit), HOME=str(config.parent), USERPROFILE=str(config.parent))
    args = [sys.executable, str(ROOT / "scripts/wb.py"), "rule-packet", "capture", "--workspace-root", str(workspace),
            "--packet-id", "task", "--stage", "implementation", "--signals", '{"operation":["edit"]}',
            "--loaded", "selected=" + hashlib.sha256(body.encode()).hexdigest()]
    result = subprocess.run(args, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "captured"
    assert json.loads(result.stdout)["selected_ids"] == ["selected"]
    inspect_args = list(args[:-2])
    inspect_args[3] = "inspect"
    result = subprocess.run(inspect_args, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "hit"


def test_canonical_workspace_id_change_invalidates_same_path_cache(stores):
    workspace, _ = stores
    capture(stores)
    (workspace / ".work-bundle/project.yaml").write_text("metadata_version: 4\nauthority: canonical\nworkspace:\n  id: replaced-workspace\n")
    result = inspect(stores)
    assert result["context_changed"] is True
    assert result["requires_agent_reassessment"] is True
    assert result["reusable_selected_ids"] == []


def test_canonical_signal_digest_is_order_independent(stores):
    import rule_packet
    workspace, roots = stores
    current = binding(workspace)
    current["observable_signals"] = {"operation": ["edit", "read"], "file_scope": ["scripts", "tests"]}
    rule_packet.capture_packet(workspace, "selected", current, loaded(roots, "toolkit"))
    current["observable_signals"] = {"file_scope": ["tests", "scripts"], "operation": ["read", "edit"]}
    assert rule_packet.inspect_packet(workspace, "selected", current)["status"] == "hit"


@pytest.mark.parametrize("change", ["added", "changed", "removed", "formatting"])
def test_direct_recapture_reports_old_index_deltas_before_new_basis(stores, change):
    _, roots = stores
    capture(stores)
    index = roots["global"] / "index.yaml"
    data = yaml.safe_load(index.read_text())
    if change == "added":
        data["rules"].append(dict(data["rules"][0], id="new", path="new.md"))
    elif change == "changed":
        data["rules"][0]["applies_when"] = ["new operation"]
    elif change == "removed":
        data["rules"] = []
    index.write_text(index.read_text() + "# changed bytes\n" if change == "formatting" else yaml.safe_dump(data))
    result = capture(stores)
    assert result["previous_packet_status"] == "refresh-required"
    assert result["requires_agent_reassessment"] is True
    assert result["index_deltas"]["indexes_changed"] == ["global"]
    assert result["index_deltas"][change] if change != "formatting" else not result["index_deltas"]["changed"]
    stored = json.loads(Path(result["packet_path"]).read_text())
    assert stored["refresh_observation"]["index_deltas"] == result["index_deltas"]
    assert inspect(stores)["status"] == "hit"
