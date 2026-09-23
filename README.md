# WorkBundle

[![CI](https://github.com/Ldsystem/work-bundle/actions/workflows/ci.yml/badge.svg)](https://github.com/Ldsystem/work-bundle/actions/workflows/ci.yml)

WorkBundle helps coding agents understand why a change is needed, work in the right repository, and check the result. It provides skills for project knowledge, focused fixes, specifications, plans, and independent review. Your intent guides the work; agents judge the content, while tools handle repeatable structure and safety checks.

## Install

You need Git and Python 3.13 or newer. Clone this repository to a location you intend to keep, then run the installer from that checkout:

```bash
git clone https://github.com/Ldsystem/work-bundle.git
cd work-bundle
python3 bin/install.py
```

On Windows, use `py -3.13 bin\install.py` instead of the last command. The installer sets up WorkBundle's local configuration and makes its skills available to agents; it does not turn your projects into WorkBundle workspaces. The installed skills point to this checkout, so keep it in place. Rerun the installer when you want to activate newly added skills.

If you use Codex or Claude, you can also register a session-start hook in an existing client configuration:

```bash
python3 bin/install.py --hooks auto
```

On Windows, use `py -3.13 bin\install.py --hooks auto`. `--hooks auto` targets Codex and Claude configuration directories that already exist; `--hooks select` lets you choose interactively. Codex may ask you to review or trust the hook before it runs.

## Use it with an agent

Open your project in an agentic client that can use the installed skills. You can ask for the outcome in ordinary language, or name a skill when you want a particular workflow:

> “Set up this repository as a WorkBundle workspace. Use `wb-initialize-project` and show me what will change before applying it.”

> “Investigate this bug using the project’s accepted decisions and current code. Make a small fix with `dev-create-task-plan`, then check the affected behavior.”

> “This feature needs a specification and a staged implementation plan. Use `orch-create-specification` and `orch-create-implementation-plan`; have a different agent review the actual result.”

WorkBundle does not require a full orchestration plan for every change. A bounded repair can stay lightweight; larger work can use specification, planning, execution, and review stages. In either path, the agent remains responsible for meaning, scope, and acceptance.

## What it provides

- **Workspace awareness:** Supports a single repository or a workspace with multiple source repositories, so an agent can work in the right checkout without confusing project files with toolkit files.
- **Durable knowledge:** `ks-*` skills help retrieve and maintain project decisions worth carrying across tasks, without treating current code as proof that it is correct.
- **Right-sized workflows:** `dev-*` skills support focused changes; `orch-*` skills support specifications, dependent tasks, handoffs, and independent reviews for larger efforts.
- **Agent-owned judgment:** Tools check necessary structure before writing and report mechanical facts. A reviewer advises; the agent leading the task decides what to repair and whether to accept it.

[Execution Flow](https://github.com/Ldsystem/execution-flow) is an optional, separate companion for executor selection and delegation. WorkBundle works without it.

> [!NOTE]
> WorkBundle's workspace files can include project knowledge and orchestration history. Keep credentials out of agent-visible files and use the dedicated credential workflow when a task requires them.
