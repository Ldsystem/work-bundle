from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import shutil

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts/orchestration"))

import phase_delivery as runtime
from test_orchestration_plans import workspace


@pytest.fixture
def delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    # Candidate identity compares bytes, so the worktree and Git object use LF.
    (candidate / "product.txt").write_bytes(b"original\n")
    bridge = candidate / "bridge.py"
    bridge.write_text('''import argparse,json,pathlib,sys
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--response');a=p.parse_args()
r=json.loads(pathlib.Path(a.request).read_text()); out={k:r[k] for k in ('protocol','role','action','session_id','plan_id','phase_id','payload_sha256','snapshot_manifest_sha256','snapshot_content_sha256')}
out.update(success=True,message=None,configuration=r['configuration'],process_token=r['process_token'],endpoints=r['endpoints'])
if r['action']=='configure':
 pathlib.Path(r['session_root'],'env.json').write_text('{}');out['configuration']={'produced_paths':['env.json'],'external_references':[]}
if r['action']=='run':out['rows']=[{'task':x['task'],'test':x['test'],'passes':True,'message':None} for x in r['selected']]
pathlib.Path(a.response).write_text(json.dumps(out))
''')
    descriptors = {}
    for role, action in [("config_env", "configure"), ("test_runner", "run")]:
        descriptors[role] = {
            "protocol": "phase-bridge-v1", "role": role,
            "argv": [sys.executable, "bridge.py"], "working_directory": ".",
            "timeouts": {"invoke_seconds": 2, "session_seconds": None},
            "ownership": None, "capabilities": [action], "credential_ids": [], "external_targets": [],
        }
    (candidate / "bridges.json").write_text(json.dumps({"protocol": "phase-bridge-v1", "bridges": descriptors}))
    for argv in (["git", "init", "-q"], ["git", "config", "core.autocrlf", "false"], ["git", "add", "."],
                 ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"]):
        subprocess.run(argv, cwd=candidate, check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=candidate, check=True, capture_output=True, text=True).stdout.strip()
    target = runtime.build_implementation_review_candidate(source_root=candidate, kind="worktree", base_commit=head, changed_paths=["product.txt"])
    (tmp_path / "candidate.json").write_text(json.dumps(target))
    policy = {
        "plan_id": "plan-test", "phase_id": "phase-test", "task_id": "task-delivery",
        "phase": {"delivery": {"mode": "executable_snapshot", "task_id": "task-delivery",
            "snapshot": {"start_required": False, "retention": "until_finalization_or_explicit_release"},
            "bridges": {"config_env": "required", "start_snapshot": "optional", "test_runner": "required"},
            "test_catalog": [{"task_id": "task-delivery", "test_id": "VAL-ONE", "disposition": "executable", "purpose": "Run fixture"}] }},
        "catalog": [{"task": "task-delivery", "test": "VAL-ONE", "process": {
            "argv": ["tool", "test"], "repository_id": "source", "working_directory": ".", "timeout_seconds": 2}}],
        "authority_identity": {"id": "task-delivery", "sha256": "a" * 64},
        "predecessors": [], "external_targets": [], "exclusions": [],
        "binding": {"execution_path": str(candidate), "repository_id": "source", "execution_id": "execution-test"},
        "accepted": None,
    }
    monkeypatch.setattr(runtime, "resolve_phase_authority", lambda *_args: policy)
    return tmp_path, candidate, policy


def test_materialize_payload_is_immutable_and_run_phase_selection_uses_snapshot(delivery):
    workspace, candidate, _policy = delivery
    facts = runtime.materialize_phase_handoff(workspace, "plan-test", "phase-test", "task-delivery", "bridges.json", workspace / "candidate.json")
    (candidate / "product.txt").write_text("downstream mutation")
    # Accepted mode consumes the immutable stored product, independent of later candidate mutation.
    bundle = runtime.read_bundle(workspace, "plan-test", "phase-test", check_authority=False)
    assert (Path(bundle["snapshot_root"]) / "product.txt").read_text() == "original\n"
    assert facts["runtime_bundle"]["payload_sha256"] == bundle["runtime_bundle"]["payload_sha256"]
    assert not list(Path(bundle["bundle_root"]).joinpath("sessions").iterdir())


def test_run_phase_all_reports_exact_boolean_rows_and_removes_session(delivery):
    workspace, _candidate, _policy = delivery
    runtime.materialize_phase_handoff(workspace, "plan-test", "phase-test", "task-delivery", "bridges.json", workspace / "candidate.json")
    outcome = runtime.run_phase(workspace, "plan-test", "phase-test", selection="all", prepare=True)
    assert outcome["rows"] == [{"task": "task-delivery", "test": "VAL-ONE", "passes": True, "message": None}]
    assert outcome["exit_code"] == 0
    assert not list((workspace / runtime.runtime_paths(workspace, "plan-test", "phase-test")["relative_path"] / "sessions").iterdir())


def test_release_payload_leaves_cleaned_identity_and_refuses_later_run(delivery):
    workspace, _candidate, _policy = delivery
    facts = runtime.materialize_phase_handoff(workspace, "plan-test", "phase-test", "task-delivery", "bridges.json", workspace / "candidate.json")
    runtime.release_phase_snapshot(workspace, "plan-test", "phase-test")
    state = json.loads((workspace / facts["runtime_bundle"]["state_relative_path"]).read_text())
    assert state["state"] == "cleaned" and state["reason"] == "explicit_release"
    with pytest.raises(runtime.PhaseDeliveryError, match="cleaned"):
        runtime.run_phase(workspace, "plan-test", "phase-test", selection="all")
    assert runtime.release_phase_snapshot(workspace, "plan-test", "phase-test")["state"] == "cleaned"


def materialize(delivery):
    workspace, _candidate, _policy = delivery
    return runtime.materialize_phase_handoff(workspace, "plan-test", "phase-test", "task-delivery", "bridges.json", workspace / "candidate.json")


def test_start_rejection_reports_observed_process_identity(delivery, monkeypatch):
    facts = supervisor_delivery(delivery)
    directory = Path(facts["bundle_root"]) / "sessions" / ("session-" + "8" * 32)
    directory.mkdir()
    lease = {"session_id": directory.name, "configuration": {"produced_paths": [], "external_references": []},
        "process_token": None, "endpoints": [], "pending_action": None}

    class Process:
        pid = 12345
        def poll(self): return None

    def launch(argv, **kwargs):
        request = json.loads(Path(argv[-3]).read_text())
        response = {**request, "success": True, "message": None, "ownership": "child_process", "pid": 54321}
        for key in ("snapshot_root", "session_root", "external_targets"):
            response.pop(key)
        response["process_token"] = "fixture-token"
        runtime._write(Path(argv[-1]), response)
        return Process()

    monkeypatch.setattr(runtime.subprocess, "Popen", launch)
    monkeypatch.setattr(runtime, "process_identity", lambda pid: {"pid": pid, "birth_time": 100.0})
    monkeypatch.setattr(runtime, "process_status", lambda identity: "alive")
    monkeypatch.setattr(runtime, "_terminate_bridge", lambda *_args: True)
    with pytest.raises(runtime.PhaseDeliveryError, match="expected PID 12345, reported PID 54321, status alive, exit code None"):
        runtime._BridgeSession(facts, directory, lease).invoke("start_snapshot", "start")


@pytest.mark.parametrize("selection,selector", [("task", "task-delivery"), ("test", "VAL-ONE"), ("all", None)])
def test_run_phase_selection_and_configuration_carry_forward(delivery, monkeypatch, selection, selector):
    materialize(delivery)
    captured = []
    invoke = runtime._BridgeSession.invoke
    def observe(self, role, action, selected=None):
        response = invoke(self, role, action, selected)
        captured.append(json.loads((self.directory / f"request-{action}.json").read_text()))
        return response
    monkeypatch.setattr(runtime._BridgeSession, "invoke", observe)
    outcome = runtime.run_phase(delivery[0], "plan-test", "phase-test", selection=selection, selector=selector)
    assert outcome["exit_code"] == 0
    assert [request["action"] for request in captured] == ["configure", "run"]
    assert captured[1]["configuration"]["produced_paths"] == ["env.json"]
    assert captured[0]["session_id"] == captured[1]["session_id"]
    assert captured[1]["external_targets"] == []
    assert captured[1]["selected"][0]["test"] == "VAL-ONE"


@pytest.mark.parametrize("selection,selector", [("task", "task-unknown"), ("test", "VAL-UNKNOWN"), ("serve", None)])
def test_run_phase_unknown_or_no_start_selection_refuses_before_session(delivery, selection, selector):
    facts = materialize(delivery)
    with pytest.raises(runtime.PhaseDeliveryError):
        runtime.run_phase(delivery[0], "plan-test", "phase-test", selection=selection, selector=selector)
    assert not list((Path(facts["bundle_root"]) / "sessions").iterdir())


@pytest.mark.parametrize("case", ["protocol", "shell", "cwd", "role", "timeout", "external", "extra"])
def test_bridge_materialize_invalid_descriptor_refuses_before_runtime_effects(delivery, case):
    workspace, candidate, _policy = delivery
    manifest = json.loads((candidate / "bridges.json").read_text())
    descriptor = manifest["bridges"]["test_runner"]
    if case == "protocol": descriptor["protocol"] = "phase-bridge-v0"
    if case == "shell": descriptor["argv"] = ["sh", "-c", "echo unsafe"]
    if case == "cwd": descriptor["working_directory"] = "../escape"
    if case == "role": descriptor["role"] = "config_env"
    if case == "timeout": descriptor["timeouts"]["invoke_seconds"] = 0
    if case == "external": descriptor["external_targets"] = [{"target_id": "remote", "authority_ref": "task-delivery#external-targets.remote", "permitted_actions": ["run"]}]
    if case == "extra": manifest["bridges"]["unknown"] = descriptor
    (candidate / "bridges.json").write_text(json.dumps(manifest))
    with pytest.raises(runtime.PhaseDeliveryError): materialize(delivery)
    assert not (workspace / ".work-bundle/orchestration/runtime").exists()


def test_materialize_supplied_candidate_mismatch_refuses_before_effects(delivery):
    workspace, candidate, _policy = delivery
    (candidate / "product.txt").write_text("changed")
    with pytest.raises(runtime.PhaseDeliveryError, match="candidate identity mismatch"):
        materialize(delivery)
    assert not (workspace / ".work-bundle/orchestration/runtime").exists()


@pytest.mark.parametrize("case", ["symlink", "credentials"])
def test_materialize_protected_or_link_entries_refuse_before_content_copy(delivery, case):
    workspace, candidate, _policy = delivery
    if case == "symlink": (candidate / "link").symlink_to(candidate / "product.txt")
    else: (candidate / "credentials").mkdir()
    with pytest.raises(runtime.PhaseDeliveryError): materialize(delivery)
    assert not (workspace / ".work-bundle/orchestration/runtime").exists()


def test_payload_digest_refuses_modified_immutable_bytes_before_session(delivery):
    facts = materialize(delivery)
    path = Path(facts["snapshot_root"]) / "product.txt"
    path.chmod(0o600); path.write_text("tampered")
    with pytest.raises(runtime.PhaseDeliveryError, match="payload bytes"):
        runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="all")
    assert not list((Path(facts["bundle_root"]) / "sessions").iterdir())


def test_preacceptance_release_and_rematerialize_repaired_candidate(delivery):
    workspace, candidate, _policy = delivery
    first = materialize(delivery)
    (candidate / "product.txt").write_text("repaired")
    runtime.release_phase_snapshot(workspace, "plan-test", "phase-test")
    target = json.loads((workspace / "candidate.json").read_text())
    target = runtime.build_implementation_review_candidate(source_root=candidate, kind="worktree", base_commit=target["base_commit"], changed_paths=["product.txt"])
    (workspace / "candidate.json").write_text(json.dumps(target))
    second = materialize(delivery)
    assert first["runtime_bundle"]["relative_path"] == second["runtime_bundle"]["relative_path"]
    assert first["runtime_bundle"]["payload_sha256"] != second["runtime_bundle"]["payload_sha256"]
    assert runtime.run_phase(workspace, "plan-test", "phase-test", selection="all")["exit_code"] == 0


class SimulatedCrash(BaseException): pass


@pytest.mark.parametrize("point", ["state", "staging", "rename"])
def test_materialize_crash_reentry_rolls_back_or_activates_exact_transaction(delivery, monkeypatch, point):
    write, verify = runtime._write, runtime._verify_payload
    def crash_write(path, value):
        if point == "state" and value.get("state") == "materializing":
            write(path, value); raise SimulatedCrash()
        if point == "rename" and value.get("state") == "active": raise SimulatedCrash()
        write(path, value)
    def crash_verify(bundle, state):
        result = verify(bundle, state)
        if point == "staging" and bundle.name.endswith(".staging"): raise SimulatedCrash()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(runtime, "_write", crash_write)
        patch.setattr(runtime, "_verify_payload", crash_verify)
        with pytest.raises(SimulatedCrash): materialize(delivery)
    facts = materialize(delivery)
    assert facts["state"] == "active"
    assert not list(Path(facts["bundle_root"]).parent.glob("*.staging"))


def test_release_cleanup_retry_after_partial_payload_deletion(delivery, monkeypatch):
    facts = materialize(delivery)
    remove = runtime._remove_tree
    def partial(path):
        target = Path(facts["snapshot_root"]) / "product.txt"
        target.parent.chmod(0o700); target.chmod(0o600); target.unlink()
        raise OSError("synthetic deletion failure")
    with monkeypatch.context() as patch:
        patch.setattr(runtime, "_remove_tree", partial)
        with pytest.raises(OSError): runtime.release_phase_snapshot(delivery[0], "plan-test", "phase-test")
    assert runtime.release_phase_snapshot(delivery[0], "plan-test", "phase-test")["state"] == "cleaned"


def test_runtime_state_unknown_fields_are_refused_before_effects(delivery):
    facts = materialize(delivery)
    path = delivery[0] / facts["runtime_bundle"]["state_relative_path"]
    value = json.loads(path.read_text()); value["acceptance"] = "invented"; path.write_text(json.dumps(value))
    with pytest.raises(runtime.PhaseDeliveryError, match="runtimeState"):
        runtime.read_bundle(delivery[0], "plan-test", "phase-test")


def test_run_phase_public_selection_parser_and_command_registration():
    import dispatcher
    commands = {"run-phase", "materialize-phase-handoff", "release-phase-snapshot"}
    assert commands.issubset(dispatcher.RECOGNIZED_COMMANDS)
    args = dispatcher.build_parser().parse_args(["run-phase", "--plan-id", "plan-test", "--phase-id", "phase-test", "--prepare", "--test", "VAL-ONE"])
    assert args.test == "VAL-ONE" and args.prepare
    with pytest.raises(SystemExit):
        dispatcher.build_parser().parse_args(["run-phase", "--plan-id", "plan-test", "--phase-id", "phase-test", "--serve", "--all"])


SUPERVISOR = '''import argparse,json,pathlib,sys,os,time,subprocess
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--response');p.add_argument('--scenario',default='normal');a=p.parse_args()
r=json.loads(pathlib.Path(a.request).read_text()); out={k:r[k] for k in ('protocol','role','action','session_id','plan_id','phase_id','payload_sha256','snapshot_manifest_sha256','snapshot_content_sha256')}
out.update(success=True,message=None,configuration=r['configuration'],process_token=r['process_token'],endpoints=r['endpoints'])
root=pathlib.Path(r['session_root']); action=r['action']; child=None
if action=='configure':
 (root/'env.json').write_text('{}');out['configuration']={'produced_paths':['env.json'],'external_references':[]}
if action=='start':
 out.update(ownership='child_process',pid=os.getpid(),process_token='fixture-token',endpoints=['http://127.0.0.1:9876'])
 child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
 (root/'child.pid').write_text(str(child.pid))
if action=='readiness' and a.scenario=='readiness-failure':out.update(success=False,message='raw readiness failure')
if action=='stop':
 (root/'stop').write_text('stop');out['stopped']=True
if action=='run':
 if a.scenario=='timeout':time.sleep(10)
 out['rows']=[{'task':x['task'],'test':x['test'],'passes':a.scenario!='test-failure','message':'raw failure' if a.scenario=='test-failure' else None} for x in r['selected']]
 if a.scenario=='bad-token':out['process_token']='foreign-token'
 if a.scenario=='extra-row':out['rows'].append(out['rows'][0])
 if a.scenario=='boolean':out['rows'][0]['passes']='true'
 if a.scenario=='bounded':out['rows'][0]['message']='x'*10000
 if a.scenario=='session':out['session_id']='session-'+'0'*32
tmp=pathlib.Path(a.response+'.tmp');tmp.write_text(json.dumps(out));tmp.replace(a.response)
if action=='start':
 while not (root/'stop').exists():time.sleep(.01)
 child.terminate();child.wait(timeout=2)
'''


def supervisor_delivery(delivery, scenario="normal", *, ownership="child_process"):
    workspace, candidate, policy = delivery
    (candidate / "bridge.py").write_text(SUPERVISOR)
    manifest = json.loads((candidate / "bridges.json").read_text())
    start = json.loads(json.dumps(manifest["bridges"]["config_env"]))
    start.update(role="start_snapshot", ownership=ownership, capabilities=["start", "readiness", "stop"], timeouts={"invoke_seconds": 2, "session_seconds": .15 if scenario == "serve" else 2})
    manifest["bridges"]["start_snapshot"] = start
    for descriptor in manifest["bridges"].values():
        descriptor["argv"] += ["--scenario", scenario]
    if scenario == "timeout": manifest["bridges"]["test_runner"]["timeouts"]["invoke_seconds"] = .2
    (candidate / "bridges.json").write_text(json.dumps(manifest))
    policy["phase"]["delivery"]["snapshot"]["start_required"] = True
    policy["phase"]["delivery"]["bridges"]["start_snapshot"] = "required"
    return materialize(delivery)


@pytest.mark.parametrize("scenario", ["normal", "readiness-failure", "test-failure", "timeout", "bad-token", "extra-row", "boolean", "session", "bounded"])
def test_run_phase_bridge_session_cleanup_owns_and_reaps_cooperative_supervisor(delivery, monkeypatch, scenario):
    facts = supervisor_delivery(delivery, scenario)
    identities = []
    remove = runtime._remove_tree
    def observe(directory):
        pidfile = directory / "child.pid"
        if pidfile.is_file():
            identities.append(int(pidfile.read_text()))
        lease = directory / "lease.json"
        if lease.is_file():
            identities.append(json.loads(lease.read_text())["child_identity"]["pid"])
        remove(directory)
    monkeypatch.setattr(runtime, "_remove_tree", observe)
    outcome = runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="all")
    assert outcome["exit_code"] == (0 if scenario in {"normal", "bounded"} else 1), outcome
    assert outcome["bridge_observations"]["stop"] == "passed", outcome
    if scenario == "test-failure": assert outcome["rows"][0]["message"] == "raw failure"
    if scenario == "bounded": assert len(outcome["rows"][0]["message"]) == runtime.MESSAGE_LIMIT
    assert identities and all(not runtime.psutil.pid_exists(pid) for pid in identities)
    assert not list((Path(facts["bundle_root"]) / "sessions").iterdir())


def test_run_phase_serve_timeout_and_interruption_use_bounded_stop(delivery, monkeypatch):
    facts = supervisor_delivery(delivery, "serve")
    outcome = runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="serve")
    assert outcome["exit_code"] == 1 and outcome["message"] == "foreground session timeout"
    invoke = runtime._BridgeSession.invoke
    def interrupt(self, role, action, selected=None):
        if action == "run": raise KeyboardInterrupt()
        return invoke(self, role, action, selected)
    monkeypatch.setattr(runtime._BridgeSession, "invoke", interrupt)
    outcome = runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="all")
    assert outcome["exit_code"] == 130 and outcome["bridge_observations"]["stop"] == "passed"
    assert not list((Path(facts["bundle_root"]) / "sessions").iterdir())


def test_release_lease_preflight_is_read_only_and_live_runner_blocks(delivery):
    facts = materialize(delivery)
    session_id = "session-" + "1" * 32
    directory = Path(facts["bundle_root"]) / "sessions" / session_id
    directory.mkdir()
    lease = {"protocol": "phase-session-lease-v1", "state": "active", "session_id": session_id,
        "plan_id": "plan-test", "phase_id": "phase-test", "payload_sha256": facts["runtime_bundle"]["payload_sha256"],
        "runner_identity": runtime.process_identity(os.getpid()), "configuration": {"produced_paths": [], "external_references": []},
        "process_token": None, "endpoints": [], "child_identity": None, "external_targets": [], "last_completed_action": None, "pending_action": None, "stop_verified": False}
    runtime._write(directory / "lease.json", lease)
    before = {path: path.read_bytes() for path in Path(facts["bundle_root"]).parent.rglob("*") if path.is_file()}
    with pytest.raises(runtime.PhaseDeliveryError, match="live or uncertain"):
        runtime.preflight_cleanup(delivery[0], "plan-test", "phase-test")
    assert {path: path.read_bytes() for path in Path(facts["bundle_root"]).parent.rglob("*") if path.is_file()} == before


def accept_fixture(delivery, facts, monkeypatch, *, mismatch=None):
    workspace, _candidate, policy = delivery
    data = {"product_identity": {"kind": "worktree", "sha256": facts["identity"]["candidate"]["sha256"]},
        "executor_result": {"id": "result-delivery", "sha256": "b" * 64}}
    handoff = {"runtime_bundle": facts["runtime_bundle"], "phase_id": "phase-test", "delivery_task_id": "task-delivery", "bridges": facts["bridges"]}
    if mismatch == "product": data["product_identity"]["sha256"] = "c" * 64
    if mismatch == "executor": data["executor_result"]["sha256"] = "c" * 64
    if mismatch == "handoff": handoff = {**handoff, "runtime_bundle": {**handoff["runtime_bundle"], "payload_sha256": "c" * 64}}
    policy["accepted"] = {"data": data}
    monkeypatch.setattr(runtime, "_artifact", lambda *_args: {"digest": "b" * 64, "data": {"phase_handoff": handoff}})


@pytest.mark.parametrize("mismatch", ["product", "executor", "handoff"])
def test_run_phase_stale_accepted_reference_never_falls_back_to_candidate(delivery, monkeypatch, mismatch):
    facts = materialize(delivery)
    accept_fixture(delivery, facts, monkeypatch, mismatch=mismatch)
    with pytest.raises(runtime.PhaseDeliveryError, match="accepted"):
        runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="all")
    with pytest.raises(runtime.PhaseDeliveryError, match="accepted"):
        runtime.release_phase_snapshot(delivery[0], "plan-test", "phase-test")


def test_accepted_payload_runs_after_downstream_candidate_mutation_with_distinct_product_manifest(delivery, monkeypatch):
    facts = materialize(delivery)
    assert facts["identity"]["candidate"]["sha256"] != facts["runtime_bundle"]["snapshot_content_sha256"]
    accept_fixture(delivery, facts, monkeypatch)
    (delivery[1] / "product.txt").write_text("later work")
    assert runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="all")["exit_code"] == 0


@pytest.mark.parametrize("ownership,scenario", [("child_process", "normal"), ("external", "normal"), ("external", "stop-failure")])
def test_release_crashed_session_requires_verified_exact_stop_before_lease_clear(delivery, monkeypatch, ownership, scenario):
    workspace, candidate, policy = delivery
    if ownership == "external":
        policy["external_targets"] = [{"target_id": "fixture", "purpose": "Synthetic external resource", "permitted_actions": ["start", "readiness", "stop"]}]
        text = SUPERVISOR.replace("ownership='child_process',pid=os.getpid(),", "ownership='external',")
        text = text.replace("if action=='start':\n while", "if action=='never':\n while")
        text = text.replace(" child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n (root/'child.pid').write_text(str(child.pid))", " pass")
        if scenario == "stop-failure": text = text.replace("out['stopped']=True", "out['stopped']=False")
        # Prepare descriptors/policy first; external mode requires exact target authority.
        supervisor_delivery(delivery)
        runtime.release_phase_snapshot(workspace, "plan-test", "phase-test")
        (candidate / "bridge.py").write_text(text)
        manifest = json.loads((candidate / "bridges.json").read_text())
        descriptor = manifest["bridges"]["start_snapshot"]
        descriptor["ownership"] = "external"
        descriptor["external_targets"] = [{"target_id": "fixture", "authority_ref": "task-delivery#external-targets.fixture", "permitted_actions": ["start", "readiness", "stop"]}]
        (candidate / "bridges.json").write_text(json.dumps(manifest))
        facts = materialize(delivery)
    else:
        facts = supervisor_delivery(delivery)
    session_id = "session-" + "2" * 32
    directory = Path(facts["bundle_root"]) / "sessions" / session_id
    directory.mkdir()
    lease = {"protocol": "phase-session-lease-v1", "state": "active", "session_id": session_id,
        "plan_id": "plan-test", "phase_id": "phase-test", "payload_sha256": facts["runtime_bundle"]["payload_sha256"],
        "runner_identity": runtime.process_identity(os.getpid()), "configuration": {"produced_paths": [], "external_references": []},
        "process_token": None, "endpoints": [], "child_identity": None, "external_targets": [], "last_completed_action": None, "pending_action": None, "stop_verified": False}
    session = runtime._BridgeSession(facts, directory, lease)
    session.persist()
    session.invoke("config_env", "configure")
    session.invoke("start_snapshot", "start")
    lease["runner_identity"]["birth_time"] -= 100  # Exact old instance is proven absent, without a PID signal.
    session.persist()
    before = (directory / "lease.json").read_bytes()
    checked = runtime.preflight_cleanup(workspace, "plan-test", "phase-test")
    assert checked["leases"][0]["recovery"] is True and (directory / "lease.json").read_bytes() == before
    if ownership == "child_process":
        # Recovery cannot waitpid another parent's child; retain the actual parent here
        # only to emulate the OS reaper while the recovery code proves disappearance.
        import threading
        thread = threading.Thread(target=lambda: session.supervisor.wait(timeout=5))
        thread.start()
    if scenario == "stop-failure":
        with pytest.raises(runtime.PhaseDeliveryError, match="stop did not verify"):
            runtime.release_phase_snapshot(workspace, "plan-test", "phase-test")
        assert directory.exists()
        assert json.loads((directory / "lease.json").read_text())["stop_verified"] is False
        with pytest.raises(runtime.PhaseDeliveryError):
            runtime.release_phase_snapshot(workspace, "plan-test", "phase-test")
        assert directory.exists()
    else:
        assert runtime.release_phase_snapshot(workspace, "plan-test", "phase-test")["state"] == "cleaned"
    if ownership == "child_process": thread.join(timeout=5)


def test_release_dead_runner_missing_child_context_retains_lease(delivery, monkeypatch):
    facts = supervisor_delivery(delivery)
    invoke = runtime._BridgeSession.invoke
    def crash(self, role, action, selected=None):
        result = invoke(self, role, action, selected)
        if action == "start":
            self.lease["runner_identity"]["birth_time"] -= 100
            self.lease["child_identity"] = None
            self.persist()
            raise SimulatedCrash()
        return result
    # Capture the cooperative supervisor solely for fixture teardown.
    sessions = []
    def capture(self, role, action, selected=None):
        sessions.append(self)
        return crash(self, role, action, selected)
    with monkeypatch.context() as patch:
        patch.setattr(runtime._BridgeSession, "invoke", capture)
        with pytest.raises(SimulatedCrash):
            runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="all")
    # run_phase's finally conservatively retains missing identity context.
    directory = sessions[-1].directory
    assert directory.exists()
    with pytest.raises(runtime.PhaseDeliveryError): runtime.release_phase_snapshot(delivery[0], "plan-test", "phase-test")
    (directory / "stop").touch()
    if sessions[-1].supervisor: sessions[-1].supervisor.wait(timeout=3)


def test_test_bridge_false_envelope_preserves_bound_raw_rows(delivery):
    bridge = delivery[1] / "bridge.py"
    bridge.write_text(bridge.read_text().replace("pathlib.Path(a.response).write_text", "out['success']=False if r['action']=='run' else True\npathlib.Path(a.response).write_text"))
    materialize(delivery)
    outcome = runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="all")
    assert outcome["exit_code"] == 1
    assert outcome["rows"] == [{"task": "task-delivery", "test": "VAL-ONE", "passes": True, "message": None}]


def test_same_candidate_content_commit_container_reuses_published_payload(delivery):
    facts = materialize(delivery)
    original = json.loads((delivery[0] / "candidate.json").read_text())
    committed = runtime.build_implementation_review_candidate(source_root=delivery[1], kind="commit", base_commit=original["base_commit"], changed_paths=["product.txt"])
    assert committed["sha256"] == original["sha256"]
    (delivery[0] / "candidate.json").write_text(json.dumps(committed))
    assert materialize(delivery)["runtime_bundle"] == facts["runtime_bundle"]


def test_session_lifetime_bounds_test_run_and_still_verifies_stop(delivery):
    facts = supervisor_delivery(delivery, "timeout")
    runtime.release_phase_snapshot(delivery[0], "plan-test", "phase-test")
    manifest = json.loads((delivery[1] / "bridges.json").read_text())
    manifest["bridges"]["start_snapshot"]["timeouts"]["session_seconds"] = .15
    manifest["bridges"]["test_runner"]["timeouts"]["invoke_seconds"] = 2
    (delivery[1] / "bridges.json").write_text(json.dumps(manifest))
    facts = materialize(delivery)
    import time
    started = time.monotonic()
    outcome = runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="all")
    assert time.monotonic() - started < 1.5
    assert outcome["exit_code"] == 1 and outcome["bridge_observations"]["stop"] == "passed"
    assert not list((Path(facts["bundle_root"]) / "sessions").iterdir())


def test_bridge_protocol_is_language_agnostic_process_boundary(delivery):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime unavailable for foreign-language bridge fixture")
    (delivery[1] / "bridge.cjs").write_text('''const fs=require('node:fs');
const args=process.argv.slice(2), request=args[args.indexOf('--request')+1], response=args[args.indexOf('--response')+1];
const r=JSON.parse(fs.readFileSync(request,'utf8')), out={};
for(const k of ['protocol','role','action','session_id','plan_id','phase_id','payload_sha256','snapshot_manifest_sha256','snapshot_content_sha256'])out[k]=r[k];
Object.assign(out,{success:true,message:null,configuration:r.configuration,process_token:r.process_token,endpoints:r.endpoints});
if(r.action==='configure'){fs.writeFileSync(r.session_root+'/env.json','{}');out.configuration={produced_paths:['env.json'],external_references:[]};}
if(r.action==='run')out.rows=r.selected.map(x=>({task:x.task,test:x.test,passes:true,message:'node process'}));
fs.writeFileSync(response,JSON.stringify(out));
''')
    manifest = json.loads((delivery[1] / "bridges.json").read_text())
    for descriptor in manifest["bridges"].values():
        descriptor["argv"] = [node, "bridge.cjs"]
    (delivery[1] / "bridges.json").write_text(json.dumps(manifest))
    materialize(delivery)
    outcome = runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="all")
    assert outcome["exit_code"] == 0 and outcome["rows"][0]["message"] == "node process", outcome


def test_materialize_authority_reads_canonical_catalog_and_exact_accepted_predecessor(workspace, tmp_path, monkeypatch):
    from test_orchestration_static_task_admission import _store_multiphase_delivery_tree
    from test_orchestration_plans import _args
    import plans
    from artifact_store import write_artifact
    _store_multiphase_delivery_tree(workspace, tmp_path)
    plans.cmd_set_plan_status(_args(workspace, id="plan-stage4", status="verified"))
    with pytest.raises(runtime.PhaseDeliveryError, match="accepted predecessor is missing"):
        runtime.resolve_phase_authority(workspace, "plan-stage4", "phase-stage4")
    accepted = {"artifact_type": "accepted-task-result", "schema_version": 2, "id": "accepted-predecessor", "plan_id": "plan-stage4", "task_id": "task-stage4",
        "authority_identity": runtime.canonical_task_authority_identity(workspace, "plan-stage4", "task-stage4"),
        "product_identity": {"kind": "worktree", "sha256": "b" * 64}, "product_sha256": "b" * 64,
        "executor_result": {"id": "result-predecessor", "sha256": "c" * 64}, "implementation_review": None,
        "validation_outcomes": [], "unresolved_material_defects": [], "knowledge_disposition": {"action": "none", "reason": "Fixture"}, "knowledge_action": "none",
        "date_created": "2026-09-30", "last_updated": "2026-09-30"}
    write_artifact(runtime.CATALOG, "accepted-task-result", {"workspace_root": workspace}, accepted, state="active", bindings={"plan": "plan-stage4", "task": "task-stage4"})
    binding = {"execution_path": str(tmp_path), "repository_id": "source", "execution_id": "execution-fixture"}
    monkeypatch.setattr(runtime, "load_task_execution_binding", lambda *_args: binding)
    facts = runtime.resolve_phase_authority(workspace, "plan-stage4", "phase-stage4")
    assert facts["task_id"] == "task-converge" and facts["binding"] == binding
    assert [(row["task"], row["test"]) for row in facts["catalog"]] == [("task-stage4", "VAL-001"), ("task-converge", "VAL-CONVERGE")]
    assert facts["predecessors"][0]["id"] == "accepted-predecessor"
    accepted["authority_identity"]["sha256"] = "d" * 64
    write_artifact(runtime.CATALOG, "accepted-task-result", {"workspace_root": workspace}, accepted, state="active", bindings={"plan": "plan-stage4", "task": "task-stage4"})
    with pytest.raises(runtime.PhaseDeliveryError, match="authority is stale"):
        runtime.resolve_phase_authority(workspace, "plan-stage4", "phase-stage4")


@pytest.mark.parametrize("alias", ["direct", "symlink", "directory-link", "hardlink"])
def test_materialize_candidate_file_protects_synthetic_vault_before_read(delivery, monkeypatch, alias):
    workspace = delivery[0]
    vault = workspace / "credentials" / "credentials.yaml"
    vault.parent.mkdir()
    vault.write_text("synthetic protected content, not a credential")
    candidate = vault
    if alias == "symlink":
        candidate = workspace / "candidate-alias.json"
        candidate.symlink_to(vault)
    elif alias == "directory-link":
        directory = workspace / "vault-alias"
        directory.symlink_to(vault.parent, target_is_directory=True)
        candidate = directory / "credentials.yaml"
    elif alias == "hardlink":
        candidate = workspace / "candidate-alias.json"
        os.link(vault, candidate)
    reads = []
    def spy(path):
        reads.append(path)
        raise AssertionError("protected semantic input reached reader")
    monkeypatch.setattr(runtime, "read_yaml_mapping", spy)
    with pytest.raises(runtime.PhaseDeliveryError, match="protected candidate input"):
        runtime.materialize_phase_handoff(workspace, "plan-test", "phase-test", "task-delivery", "bridges.json", candidate)
    assert reads == []
    assert not (workspace / ".work-bundle/orchestration/runtime").exists()


@pytest.mark.parametrize("status", [0, 23])
def test_run_phase_serve_propagates_observed_supervisor_exit_and_cli(delivery, monkeypatch, status):
    supervisor_delivery(delivery)
    runtime.release_phase_snapshot(delivery[0], "plan-test", "phase-test")
    bridge = delivery[1] / "bridge.py"
    bridge.write_text(bridge.read_text().replace("if action=='start':\n while", f"if action=='start':\n time.sleep(.3);child.terminate();child.wait(timeout=2);sys.exit({status})\n while"))
    facts = materialize(delivery)
    outcome = runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="serve")
    assert outcome["exit_code"] == int(status != 0)
    assert outcome["message"] == f"supervisor exited {status}"
    assert outcome["bridge_observations"]["stop"] == "passed"
    assert not list((Path(facts["bundle_root"]) / "sessions").iterdir())
    import argparse
    monkeypatch.setattr(runtime, "resolve_workspace_root", lambda _args: delivery[0])
    args = argparse.Namespace(plan_id="plan-test", phase_id="phase-test", serve=True, all=False, task=None, test=None, prepare=False)
    if status:
        with pytest.raises(SystemExit) as exited:
            runtime.cmd_run_phase(args)
        assert exited.value.code != 0
    else:
        assert runtime.cmd_run_phase(args) is None


def test_materialize_candidate_file_accepts_external_builder_input(delivery, tmp_path_factory):
    external = tmp_path_factory.mktemp("semantic-input") / "candidate.json"
    target = runtime.build_implementation_review_candidate(source_root=delivery[1], kind="worktree", base_commit=json.loads((delivery[0] / "candidate.json").read_text())["base_commit"], changed_paths=["product.txt"])
    external.write_text(json.dumps(target))
    assert not external.is_relative_to(delivery[0])
    facts = runtime.materialize_phase_handoff(delivery[0], "plan-test", "phase-test", "task-delivery", "bridges.json", external)
    assert facts["identity"]["candidate"] == target


@pytest.mark.parametrize("failure", ["cleanup", "integrity"])
def test_run_phase_serve_retains_exit_and_subsequent_raw_error(delivery, monkeypatch, failure):
    supervisor_delivery(delivery)
    runtime.release_phase_snapshot(delivery[0], "plan-test", "phase-test")
    bridge = delivery[1] / "bridge.py"
    bridge.write_text(bridge.read_text().replace("if action=='start':\n while", "if action=='start':\n time.sleep(.3);child.terminate();child.wait(timeout=2);sys.exit(23)\n while"))
    materialize(delivery)
    raw_error = f"fixture raw {failure} failure"
    if failure == "cleanup":
        cleanup = runtime._BridgeSession.cleanup
        def fail_cleanup(self, **kwargs):
            cleanup(self, **kwargs)
            raise runtime.PhaseDeliveryError(raw_error)
        monkeypatch.setattr(runtime._BridgeSession, "cleanup", fail_cleanup)
    else:
        verify = runtime._verify_payload
        calls = []
        def fail_integrity(*args):
            result = verify(*args)
            calls.append(True)
            if len(calls) == 2:
                raise runtime.PhaseDeliveryError(raw_error)
            return result
        monkeypatch.setattr(runtime, "_verify_payload", fail_integrity)
    outcome = runtime.run_phase(delivery[0], "plan-test", "phase-test", selection="serve")
    assert outcome["exit_code"] != 0
    assert "supervisor exited 23" in outcome["message"] and raw_error in outcome["message"]
    assert len(outcome["message"]) <= runtime.MESSAGE_LIMIT
