"""Native stage receipt fixtures; only the OS process boundary is stubbed by default."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/work-bundle"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/orchestration"))
import reviewer_workspace
import review_runtime


def bind_review_receipt(root, record, *, real_process=False, execution_id=None):
    review = deepcopy(record)
    review.pop("reviewer_run", None)
    review["review_id"] = f"review-{uuid.uuid4()}"
    area = "spec" if review["stage"] == "specification" else "plan"
    from execution_context import _read_structured
    target = next(path for path in (root / f".work-bundle/orchestration/{area}").glob("*/*.md")
                  if _read_structured(path)[0].get("id") == review["target_identity"]["artifact_id"])
    locator = "control:" + target.relative_to(root).as_posix()
    protected = root / ".work-bundle/protected-test"
    protected.mkdir(parents=True, exist_ok=True)
    context = {"stage": review["stage"], "target_identity": review["target_identity"], "target_locator": locator,
               "agent_id": review["reviewer"]["agent_id"], "capability": review["reviewer"]["capability"],
               "execution_id": execution_id or f"worker-{uuid.uuid4()}",
               "evidence_mode": "direct_source" if review["evidence"]["mode"] == "direct" else review["evidence"]["mode"]}
    packet = reviewer_workspace.build_direct_evidence_packet(source_root=root, control_root=root,
        protected_roots=[protected], artifacts=[locator], search_roots=[], validators=[], sentinels=[],
        network_state="denied", stage_review_context=context)
    created = reviewer_workspace.create_reviewer_workspace(review_runtime.reviewer_runtime_root(root), review["review_id"], packet)
    workspace = Path(created["workspace_path"])
    output = json.dumps(review)
    if real_process:
        # A separate sandboxed fixture worker inspects frozen evidence before emitting its verdict.
        argv = ["/bin/sh", "-c", 'test -r "$1" && printf "%s" "$2"', "reviewer",
                "evidence/" + locator.replace(":", "/", 1), output]
        receipt = reviewer_workspace.run_sandboxed_reviewer(workspace, argv)
    else:
        with patch.object(reviewer_workspace, "_run_sandboxed_process",
                          return_value=subprocess.CompletedProcess(["fixture-worker"], 0, output, "")):
            receipt = reviewer_workspace.run_sandboxed_reviewer(workspace, ["fixture-worker"])
    receipt_path = Path(receipt["receipt_path"])
    review["reviewer_run"] = {"run_id": receipt["run_id"], "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
    return review
