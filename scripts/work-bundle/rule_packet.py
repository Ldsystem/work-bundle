"""Disposable reuse of explicitly selected, previously loaded rule bodies.

Digests measure bytes and declared relationships, never applicability or whether
an agent actually read a body. Selection and reassessment remain caller duties.
Deleting a packet is an ordinary cache miss; it is not execution authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone

import rules
from core import out


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _body_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _binding(workspace: Path, binding: dict[str, object]) -> dict[str, object]:
    if not isinstance(binding, dict) or set(binding) != {"workspace_root", "packet_id", "lifecycle_stage", "observable_signals"}:
        raise ValueError("binding_shape")
    for field in ("workspace_root", "packet_id", "lifecycle_stage"):
        if not isinstance(binding[field], str) or not binding[field].strip():
            raise ValueError(f"binding_invalid:{field}")
    if Path(binding["workspace_root"]).resolve() != workspace.resolve():
        raise ValueError("workspace_binding_mismatch")
    signals = binding["observable_signals"]
    if not isinstance(signals, dict) or not signals or any(
        not isinstance(key, str) or not key.strip() or not isinstance(values, list)
        or any(not isinstance(item, str) or not item.strip() for item in values)
        for key, values in signals.items()
    ):
        raise ValueError("observable_signals_shape")
    metadata = rules.load_rule_yaml((workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("metadata_version") != 4 or metadata.get("authority") != "canonical":
        raise ValueError("canonical_workspace_metadata_required")
    workspace_metadata = metadata.get("workspace")
    workspace_id = workspace_metadata.get("id") if isinstance(workspace_metadata, dict) else None
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError("canonical_workspace_id_required")
    canonical_signals = {key: sorted(set(values)) for key, values in sorted(signals.items())}
    return {"workspace_root": str(workspace.resolve()), "observable_signals": canonical_signals,
            "context_binding": {"workspace_id": workspace_id, "controller_or_task_packet_id": binding["packet_id"],
                                "lifecycle_stage": binding["lifecycle_stage"], "operation_signal_digest": _digest(canonical_signals)}}


def packet_path(workspace: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name):
        raise ValueError("packet_name_invalid")
    workspace = workspace.resolve()
    path = workspace / ".work-bundle/runtime/rule-packets" / f"{name}.json"
    for candidate in (path, *list(path.parents)[:3]):
        if candidate.is_symlink():
            raise ValueError("packet_path_symlink")
    return path


def _snapshot(workspace: Path) -> tuple[dict[str, object], dict[str, dict[str, object]], list[str]]:
    registry = rules.build_effective_rule_registry(workspace)
    indexes = {}
    for source in registry["discovered"]:
        path = Path(source["index_path"])
        indexes[source["scope"]] = {
            **source, "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        }
    entries = {entry["id"]: entry for entry in registry["rules"]}
    return indexes, entries, registry["failures"]


def _selected_records(entries: dict[str, dict[str, object]], selected: set[str]) -> dict[str, object]:
    records = {}
    for rule_id in sorted(selected):
        if rule_id not in entries:
            raise ValueError(f"selected_rule_unknown:{rule_id}")
        entry = entries[rule_id]
        for required in entry["requires"]:
            if required not in selected:
                raise ValueError(f"selected_dependency_missing:{rule_id}:{required}")
        path = Path(entry["body_path"])
        if not path.is_file():
            raise ValueError(f"selected_body_missing:{rule_id}:{path}")
        # Decode without universal-newline translation: CRLF changes invalidate reuse.
        body = path.read_bytes().decode("utf-8")
        front, _ = rules.split_front_matter(body)
        if front is None or rules.metadata_shape_failures(front):
            raise ValueError(f"selected_body_metadata_invalid:{rule_id}")
        for field in rules.INDEX_FIELDS:
            if field != "path" and front[field] != entry[field]:
                raise ValueError(f"selected_body_mirror_mismatch:{rule_id}:{field}")
        records[rule_id] = {"entry": entry, "entry_digest": _digest(entry),
                            "index_entry_digest": _digest({field: entry[field] for field in rules.INDEX_FIELDS}),
                            "body_digest": _body_digest(body), "body": body}

    def closure(rule_id):
        dependencies = set()
        pending = list(entries[rule_id]["requires"])
        while pending:
            required = pending.pop()
            if required not in dependencies:
                dependencies.add(required)
                pending.extend(entries[required]["requires"])
        return {required: {key: records[required][key] for key in ("entry_digest", "body_digest")}
                for required in sorted(dependencies)}

    for rule_id in records:
        records[rule_id]["dependencies"] = closure(rule_id)
        records[rule_id]["dependency_digest"] = _digest(records[rule_id]["dependencies"])
    return records


def _require_untracked_runtime(workspace: Path, path: Path) -> None:
    probe = subprocess.run(["git", "-C", str(workspace), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if probe.returncode != 0:
        return  # A non-Git workspace has no version-controlled packet state.
    tracked = subprocess.run(["git", "-C", str(workspace), "ls-files", "--", str(path)], capture_output=True, text=True)
    ignored = subprocess.run(["git", "-C", str(workspace), "check-ignore", "--quiet", "--", str(path)], capture_output=True)
    if tracked.returncode != 0 or tracked.stdout.strip() or ignored.returncode != 0:
        raise ValueError("packet_runtime_must_be_untracked_and_ignored")


def capture_packet(workspace: Path, name: str, binding: dict[str, object], loaded_digests: dict[str, str]) -> dict[str, object]:
    workspace = workspace.resolve()
    binding = _binding(workspace, binding)
    path = packet_path(workspace, name)
    if not isinstance(loaded_digests, dict) or any(not isinstance(key, str) or not isinstance(value, str)
        or not re.fullmatch(r"[0-9a-f]{64}", value) for key, value in loaded_digests.items()):
        raise ValueError("loaded_digests_shape")
    indexes, entries, failures = _snapshot(workspace)
    if failures:
        raise ValueError(";".join(failures))
    for rule_id, entry in entries.items():
        if entry["load"] == "always" and rule_id not in loaded_digests:
            raise ValueError(f"always_rule_not_loaded:{rule_id}")
    records = _selected_records(entries, set(loaded_digests))
    for rule_id, digest in loaded_digests.items():
        if records[rule_id]["body_digest"] != digest:
            raise ValueError(f"loaded_digest_mismatch:{rule_id}")
    _require_untracked_runtime(workspace, path)
    previous = _read_packet(path)
    # Compute and retain the old-to-current observation before replacing its basis.
    # It reports mechanics only; it neither confirms nor requires a receipt for reassessment.
    refresh_observation = _comparison_observation(previous, binding, indexes, entries, records)
    selected_rules = [{"id": rule_id, "scope": record["entry"]["store_scope"], "path": record["entry"]["path"],
                       "index_entry_digest": record["index_entry_digest"], "body_digest": record["body_digest"],
                       "dependency_ids": record["entry"]["requires"]} for rule_id, record in sorted(records.items())]
    packet = {"schema_version": 1, "disposable": True, "context_binding": binding["context_binding"],
              "selected_rules": selected_rules, "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "refresh_observation": refresh_observation,
              "comparison": {"workspace_root": binding["workspace_root"], "observable_signals": binding["observable_signals"],
                             "indexes": indexes, "entries": entries, "selected_bodies": records}}
    packet["integrity_digest"] = _digest(packet)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            json.dump(packet, handle, sort_keys=True, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return {**refresh_observation, "previous_packet_status": refresh_observation["status"], "status": "captured",
            "packet_path": str(path), "selected_ids": sorted(records), "disposable": True}


def _read_packet(path: Path) -> dict[str, object] | None:
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(packet, dict) or packet.get("schema_version") != 1 or packet.get("disposable") is not True:
            return None
        digest = packet.pop("integrity_digest", None)
        if digest != _digest(packet) or set(packet) != {"schema_version", "disposable", "context_binding", "selected_rules", "created_at", "comparison", "refresh_observation"}:
            return None
        if not isinstance(packet["context_binding"], dict) or not isinstance(packet["selected_rules"], list) or not isinstance(packet["created_at"], str):
            return None
        comparison = packet["comparison"]
        if not isinstance(comparison, dict) or any(not isinstance(comparison.get(key), dict) for key in ("indexes", "entries", "selected_bodies")):
            return None
        return packet
    except (OSError, ValueError, TypeError):
        return None


def _index_deltas(cached: dict[str, object], indexes: dict[str, object], entries: dict[str, object]) -> dict[str, object]:
    comparison = cached["comparison"]
    previous = comparison["entries"]
    return {
        "added": sorted(set(entries) - set(previous)),
        "removed": sorted(set(previous) - set(entries)),
        "changed": sorted(rule_id for rule_id in set(previous) & set(entries) if previous[rule_id] != entries[rule_id]),
        "indexes_changed": sorted(scope for scope in set(indexes) | set(comparison["indexes"])
                                  if indexes.get(scope) != comparison["indexes"].get(scope)),
    }


def _comparison_observation(cached, binding, indexes, entries, selected):
    if cached is None:
        return {"status": "miss", "requires_agent_reassessment": True,
                "index_deltas": {"added": [], "changed": [], "removed": [], "indexes_changed": []},
                "context_changed": False, "reusable_selected_ids": [], "reload_selected_ids": []}
    comparison = cached["comparison"]
    deltas = _index_deltas(cached, indexes, entries)
    same_context = cached["context_binding"] == binding["context_binding"] and comparison["workspace_root"] == binding["workspace_root"]
    reusable = sorted(rule_id for rule_id, record in selected.items() if same_context and record == comparison["selected_bodies"].get(rule_id))
    reload_ids = sorted(set(comparison["selected_bodies"]) - set(reusable))
    reassess = not same_context or any(deltas.values()) or bool(reload_ids)
    return {"status": "refresh-required" if reassess else "hit", "requires_agent_reassessment": reassess,
            "index_deltas": deltas, "context_changed": not same_context,
            "reusable_selected_ids": reusable, "reload_selected_ids": reload_ids,
            "reuse_condition": "Agent reassesses applicability for every index delta before reusing unchanged selected bodies."}


def inspect_packet(workspace: Path, name: str, binding: dict[str, object]) -> dict[str, object]:
    workspace = workspace.resolve()
    binding = _binding(workspace, binding)
    path = packet_path(workspace, name)
    cached = _read_packet(path)
    if cached is None:
        return {"status": "miss", "packet_path": str(path), "requires_agent_reassessment": True,
                "reusable_selected_ids": [], "reload_selected_ids": []}
    try:
        _require_untracked_runtime(workspace, path)
        indexes, entries, failures = _snapshot(workspace)
    except (OSError, ValueError) as exc:
        return {"status": "blocked", "failures": [str(exc)], "requires_agent_reassessment": True,
                "reusable_selected_ids": []}
    comparison = cached["comparison"]
    deltas = _index_deltas(cached, indexes, entries)
    if failures:
        return {"status": "blocked", "failures": failures, "requires_agent_reassessment": True,
                "index_deltas": deltas, "entry_deltas_complete": False, "reusable_selected_ids": []}
    try:
        selected = _selected_records(entries, set(comparison["selected_bodies"]) & set(entries))
    except (OSError, ValueError) as exc:
        return {"status": "blocked", "failures": [str(exc)], "requires_agent_reassessment": True,
                "index_deltas": deltas, "reusable_selected_ids": []}
    return {**_comparison_observation(cached, binding, indexes, entries, selected), "packet_path": str(path)}


def cmd_rule_packet(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py rule-packet")
    parser.add_argument("action", choices=("capture", "inspect"))
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--name", default="selected")
    parser.add_argument("--packet-id", required=True, help="Exact canonical/runtime controller or task packet ID supplied by the agent.")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--signals", required=True, help="JSON mapping of observable signal names to string lists; agent supplied.")
    parser.add_argument("--loaded", action="append", default=[], help="Previously loaded, agent-selected rule ID=SHA256; repeat for dependencies.")
    args = parser.parse_args(argv)
    try:
        binding = {"workspace_root": str(args.workspace_root.resolve()), "packet_id": args.packet_id,
                   "lifecycle_stage": args.stage, "observable_signals": json.loads(args.signals)}
        if args.action == "capture":
            loaded = {}
            for item in args.loaded:
                rule_id, digest = item.split("=", 1)
                if rule_id in loaded:
                    raise ValueError(f"duplicate_loaded_id:{rule_id}")
                loaded[rule_id] = digest
            result = capture_packet(args.workspace_root, args.name, binding, loaded)
        else:
            if args.loaded:
                raise ValueError("inspect_does_not_select_rules")
            result = inspect_packet(args.workspace_root, args.name, binding)
    except (OSError, ValueError) as exc:
        out({"status": "blocked", "failures": [str(exc)]})
        return 1
    out(result)
    return 1 if result["status"] == "blocked" else 0
