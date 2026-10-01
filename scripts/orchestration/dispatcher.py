#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
from doctor import cmd_doctor
from execution_context import (
    cmd_build_implementation_review_candidate,
    cmd_build_task_brief,
)
from handoffs import (
    cmd_index_executor_results,
    cmd_list_executor_results,
    cmd_transition_executor_result,
    cmd_write_executor_result,
)
from init import cmd_init
from review_runtime import (
    cmd_list_accepted_task_results,
    cmd_list_final_workflow_reviews,
    cmd_list_implementation_reviews,
    cmd_write_accepted_task_result,
    cmd_write_final_workflow_review,
    cmd_write_implementation_review,
)
from repository_preflight import cmd_repository_preflight


def _lazy_command(module_name: str, function_name: str):
    """Keep unrelated lifecycle modules outside the selected command graph."""

    def invoke(args: argparse.Namespace) -> None:
        function = getattr(importlib.import_module(module_name), function_name)
        function(args)

    return invoke


cmd_write_spec = _lazy_command("specs", "cmd_write_spec")
cmd_list_specs = _lazy_command("specs", "cmd_list_specs")
cmd_set_spec_status = _lazy_command("specs", "cmd_set_spec_status")
cmd_index_specs = _lazy_command("specs", "cmd_index_specs")
cmd_write_plan = _lazy_command("plans", "cmd_write_plan")
cmd_list_plans = _lazy_command("plans", "cmd_list_plans")
cmd_set_plan_status = _lazy_command("plans", "cmd_set_plan_status")
cmd_index_plans = _lazy_command("plans", "cmd_index_plans")
cmd_write_phase = _lazy_command("plans", "cmd_write_phase")
cmd_write_task = _lazy_command("plans", "cmd_write_task")
cmd_amend_task = _lazy_command("plans", "cmd_amend_task")
cmd_finalize_reviewed_plan = _lazy_command("plans", "cmd_finalize_reviewed_plan")
cmd_git_status = _lazy_command("documents", "cmd_git_status")
cmd_next_action_candidates = _lazy_command("documents", "cmd_next_action_candidates")
cmd_related = _lazy_command("documents", "cmd_related")
cmd_state = _lazy_command("documents", "cmd_state")
cmd_write_doc = _lazy_command("documents", "cmd_write_doc")
cmd_materialize_phase_handoff = _lazy_command("phase_delivery", "cmd_materialize_phase_handoff")
cmd_run_phase = _lazy_command("phase_delivery", "cmd_run_phase")
cmd_release_phase_snapshot = _lazy_command("phase_delivery", "cmd_release_phase_snapshot")
cmd_scaffold = _lazy_command("scaffolds", "cmd_scaffold")

RECOGNIZED_COMMANDS = frozenset({
    "init", "doctor", "state", "next-action-candidates", "git-status", "scaffold",
    "repository-preflight", "build-task-brief",
    "related", "write-doc", "write-spec",
    "list-specs", "set-spec-status", "index-specs", "write-plan", "list-plans",
    "set-plan-status", "index-plans", "write-phase", "write-task", "amend-task",
    "write-executor-result", "list-executor-results",
    "transition-executor-result", "index-executor-results",
    "build-implementation-review-candidate", "write-implementation-review",
    "list-implementation-reviews", "write-accepted-task-result",
    "list-accepted-task-results", "write-final-workflow-review",
    "list-final-workflow-reviews", "finalize-reviewed-plan",
    "materialize-phase-handoff", "run-phase", "release-phase-snapshot",
})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root")
    parser.add_argument("--workspace-root")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--project-root", default=argparse.SUPPRESS)
    parent.add_argument("--workspace-root", default=argparse.SUPPRESS)
    parent.add_argument("--workspace-id")
    parent.add_argument("--execution-id")
    parent.add_argument("--repository-id")
    parent.add_argument("--execution-runtime-root")
    sub = parser.add_subparsers(dest="command", required=True)
    from scaffolds import SUPPORTED_FAMILIES
    scaffold = sub.add_parser("scaffold", parents=[parent], help="Print a read-only semantic-input shell for an explicit current family")
    scaffold.add_argument("--family", choices=tuple(SUPPORTED_FAMILIES), required=True)
    for option in ("id", "title", "purpose", "component", "version", "status", "source-spec-id", "plan-id", "phase-id", "task-id", "source-root"):
        scaffold.add_argument("--" + option)
    scaffold.add_argument("--source-id", action="append", default=[])
    scaffold.set_defaults(func=cmd_scaffold)
    sub.add_parser("init", parents=[parent]).set_defaults(func=cmd_init)
    sub.add_parser("doctor", parents=[parent]).set_defaults(func=cmd_doctor)
    sub.add_parser("state", parents=[parent]).set_defaults(func=cmd_state)
    sub.add_parser("next-action-candidates", parents=[parent]).set_defaults(func=cmd_next_action_candidates)
    sub.add_parser("git-status", parents=[parent]).set_defaults(func=cmd_git_status)
    repository_preflight = sub.add_parser("repository-preflight", parents=[parent])
    repository_preflight.add_argument("--task-file", action="append", default=[])
    repository_preflight.add_argument("--reference", action="append", default=[])
    repository_preflight.add_argument("--repository", action="append", default=[])
    repository_preflight.add_argument(
        "--accepted-baseline",
        help="JSON file containing accepted repository baselines that reconcile observed branch or commit drift",
    )
    repository_preflight.set_defaults(func=cmd_repository_preflight)
    task_brief = sub.add_parser("build-task-brief", parents=[parent])
    task_brief.add_argument("--task", required=True)
    task_brief.set_defaults(func=cmd_build_task_brief)
    related = sub.add_parser("related", parents=[parent])
    related.add_argument("--id", required=True)
    related.set_defaults(func=cmd_related)
    write_doc = sub.add_parser("write-doc", parents=[parent])
    write_doc.add_argument("--title", required=True)
    write_doc.add_argument("--content-file", required=True)
    write_doc.set_defaults(func=cmd_write_doc)
    write_spec = sub.add_parser("write-spec", parents=[parent])
    write_spec.add_argument("--title", required=True)
    write_spec.add_argument("--purpose", required=True)
    write_spec.add_argument("--component", required=True)
    write_spec.add_argument("--version", default="1")
    write_spec.add_argument("--content-file", required=True)
    write_spec.add_argument("--status", default="draft")
    write_spec.add_argument("--id")
    write_spec.set_defaults(func=cmd_write_spec)
    list_specs = sub.add_parser("list-specs", parents=[parent])
    list_specs.add_argument("--status")
    list_specs.set_defaults(func=cmd_list_specs)
    set_spec = sub.add_parser("set-spec-status", parents=[parent])
    set_spec.add_argument("--id", required=True)
    set_spec.add_argument("--status", required=True)
    set_spec.set_defaults(func=cmd_set_spec_status)
    sub.add_parser("index-specs", parents=[parent]).set_defaults(func=cmd_index_specs)
    write_plan = sub.add_parser("write-plan", parents=[parent])
    write_plan.add_argument("--title", required=True)
    write_plan.add_argument("--purpose", required=True)
    write_plan.add_argument("--component", required=True)
    write_plan.add_argument("--version", default="1")
    write_plan.add_argument("--content-file", required=True)
    write_plan.add_argument("--status", default="draft")
    write_plan.add_argument("--id")
    write_plan.add_argument("--source-spec-id", required=True)
    write_plan.add_argument("--filename")
    write_plan.set_defaults(func=cmd_write_plan)
    list_plans = sub.add_parser("list-plans", parents=[parent])
    list_plans.add_argument("--status")
    list_plans.add_argument("--kind", choices=["plan", "phase", "task"])
    list_plans.set_defaults(func=cmd_list_plans)
    set_plan = sub.add_parser("set-plan-status", parents=[parent])
    set_plan.add_argument("--id", required=True)
    set_plan.add_argument("--status", required=True)
    set_plan.add_argument("--kind", choices=["plan", "phase", "task"])
    set_plan.add_argument("--plan-id")
    set_plan.set_defaults(func=cmd_set_plan_status)
    sub.add_parser("index-plans", parents=[parent]).set_defaults(func=cmd_index_plans)
    write_phase = sub.add_parser("write-phase", parents=[parent])
    write_phase.add_argument("--plan-id", required=True)
    write_phase.add_argument("--phase-id", required=True)
    write_phase.add_argument("--title", required=True)
    write_phase.add_argument("--content-file", required=True)
    write_phase.add_argument("--status", default="planned")
    write_phase.set_defaults(func=cmd_write_phase)
    write_task = sub.add_parser("write-task", parents=[parent])
    write_task.add_argument("--plan-id", required=True)
    write_task.add_argument("--phase-id", required=True)
    write_task.add_argument("--task-id", required=True)
    write_task.add_argument("--title", required=True)
    write_task.add_argument("--content-file", required=True)
    write_task.add_argument("--status", default="planned")
    write_task.set_defaults(func=cmd_write_task)
    amend_task = sub.add_parser("amend-task", parents=[parent])
    amend_task.add_argument("--plan-id", required=True)
    amend_task.add_argument("--phase-id", required=True)
    amend_task.add_argument("--task-id", required=True)
    amend_task.add_argument("--title", required=True)
    amend_task.add_argument("--content-file", required=True)
    amend_task.add_argument("--status", default="planned")
    amend_task.set_defaults(func=cmd_amend_task)
    write_result = sub.add_parser("write-executor-result", parents=[parent])
    for flag in ("id", "plan-id", "task-id", "content-file"):
        write_result.add_argument(f"--{flag}", required=True, **(
            {"help": "Artifact ID: result-[a-z0-9][a-z0-9-]*"} if flag == "id" else {}
        ))
    write_result.add_argument("--phase-id")
    write_result.set_defaults(func=cmd_write_executor_result)
    list_results = sub.add_parser("list-executor-results", parents=[parent])
    list_results.add_argument("--plan-id")
    list_results.add_argument("--task-id")
    list_results.set_defaults(func=cmd_list_executor_results)
    transition_result = sub.add_parser("transition-executor-result", parents=[parent])
    for flag in ("id", "plan-id", "task-id", "current-state", "target-state"):
        transition_result.add_argument(f"--{flag}", required=True)
    transition_result.set_defaults(func=cmd_transition_executor_result)
    sub.add_parser("index-executor-results", parents=[parent]).set_defaults(func=cmd_index_executor_results)
    candidate = sub.add_parser("build-implementation-review-candidate", parents=[parent])
    candidate.add_argument("--source-root", required=True)
    candidate.add_argument("--kind", choices=["commit", "worktree"], required=True)
    commit_input = candidate.add_mutually_exclusive_group(required=True)
    commit_input.add_argument("--candidate-commit", help="Canonical reviewed commit (required for --kind commit)")
    commit_input.add_argument("--base-commit", help="Canonical worktree baseline (required for --kind worktree)")
    candidate.add_argument("--changed-path", action="append", default=[])
    candidate.set_defaults(func=cmd_build_implementation_review_candidate)
    for command, function, task_optional in (
        ("write-implementation-review", cmd_write_implementation_review, True),
        ("write-accepted-task-result", cmd_write_accepted_task_result, False),
        ("write-final-workflow-review", cmd_write_final_workflow_review, None),
    ):
        current = sub.add_parser(command, parents=[parent])
        prefix = {"write-implementation-review": "review", "write-accepted-task-result": "accepted",
                  "write-final-workflow-review": "final"}[command]
        current.add_argument("--id", required=True, help=f"Artifact ID: {prefix}-[a-z0-9][a-z0-9-]*")
        current.add_argument("--plan-id", required=True)
        if task_optional is not None:
            current.add_argument("--task-id", required=not task_optional)
        if command == "write-implementation-review":
            current.add_argument("--source-root", required=True)
        current.add_argument("--content-file", required=True)
        current.set_defaults(func=function)
    for command, function, has_task in (
        ("list-implementation-reviews", cmd_list_implementation_reviews, True),
        ("list-accepted-task-results", cmd_list_accepted_task_results, True),
        ("list-final-workflow-reviews", cmd_list_final_workflow_reviews, False),
    ):
        current = sub.add_parser(command, parents=[parent])
        current.add_argument("--plan-id")
        if has_task:
            current.add_argument("--task-id")
        current.set_defaults(func=function)
    finalize = sub.add_parser("finalize-reviewed-plan", parents=[parent])
    finalize.add_argument("--plan-id", required=True)
    finalize.add_argument("--final-review-id", required=True)
    finalize.set_defaults(func=cmd_finalize_reviewed_plan)
    materialize = sub.add_parser("materialize-phase-handoff", parents=[parent])
    for option in ("plan-id", "phase-id", "task-id", "bridge-manifest", "candidate-file"):
        materialize.add_argument("--" + option, required=True)
    materialize.set_defaults(func=cmd_materialize_phase_handoff)
    runner = sub.add_parser("run-phase", parents=[parent])
    runner.add_argument("--plan-id", required=True)
    runner.add_argument("--phase-id", required=True)
    runner.add_argument("--prepare", action="store_true")
    selection = runner.add_mutually_exclusive_group(required=True)
    selection.add_argument("--serve", action="store_true")
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--task")
    selection.add_argument("--test")
    runner.set_defaults(func=cmd_run_phase)
    release = sub.add_parser("release-phase-snapshot", parents=[parent])
    release.add_argument("--plan-id", required=True)
    release.add_argument("--phase-id", required=True)
    release.set_defaults(func=cmd_release_phase_snapshot)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
