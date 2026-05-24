from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

REQUIRED_PROJECT_GITIGNORE = ['.work-bundle/', 'AGENTS.md']
WORK_BUNDLE_IGNORES = ['*.secret','*.key','*.pem','.env','.env.*','cache/','tmp/','temp','.DS_Store','*.zip','*.tar','*.gz','*.7z','*.log','.cursor/','.idea/','.vscode/']

def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''

def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')

def ensure_lines(path: Path, lines: list[str]) -> bool:
    current = read_text(path).splitlines()
    changed = False
    for line in lines:
        if line not in current:
            current.append(line); changed = True
    if changed or not path.exists():
        write_text(path, '\n'.join(current).rstrip() + '\n')
    return changed

def inspect(project_root: Path) -> dict:
    wb = project_root / '.work-bundle'
    pgi = read_text(project_root / '.gitignore').splitlines()
    return {
        'project_root': str(project_root),
        'project_git': (project_root / '.git').exists(),
        'project_gitignore': (project_root / '.gitignore').exists(),
        'project_ignores_work_bundle': any(x in pgi for x in ['.work-bundle/','.work-bundle','/.work-bundle']),
        'project_ignores_agents': any(x in pgi for x in ['AGENTS.md','/AGENTS.md']),
        'agents_md': (project_root / 'AGENTS.md').exists(),
        'work_bundle': wb.exists(),
        'work_bundle_git': (wb / '.git').exists(),
        'work_bundle_gitignore': (wb / '.gitignore').exists(),
        'knowledge_root': (wb / 'knowledge').exists(),
        'orchestration_root': (wb / 'orchestration').exists(),
        'bootstrap_root': (wb / 'orchestration' / 'bootstrap').exists(),
        'repository_binding': (wb / 'orchestration' / 'bootstrap' / 'repository-binding.md').exists(),
        'agent_bootstrap': (wb / 'orchestration' / 'bootstrap' / 'agent-bootstrap.md').exists(),
        'domain_profile': (wb / 'orchestration' / 'bootstrap' / 'project-domain-profile.yaml').exists(),
        'rules_root': (project_root / 'references' / 'rules').exists(),
        'rule_contract': (project_root / 'references' / 'rules' / 'contract.yaml').exists(),
        'rule_index': (project_root / 'references' / 'rules' / 'index.yaml').exists(),
    }

def validate(project_root: Path, include_bootstrap: bool = False) -> tuple[bool, dict]:
    data = inspect(project_root)
    required = ['project_gitignore','project_ignores_work_bundle','project_ignores_agents','agents_md','work_bundle','work_bundle_gitignore','knowledge_root','orchestration_root','bootstrap_root','repository_binding','rules_root','rule_contract','rule_index']
    if include_bootstrap:
        required += ['agent_bootstrap','domain_profile']
    failures = [k for k in required if not data.get(k)]
    data['status'] = 'passed' if not failures else 'issues-found'
    data['failures'] = failures
    return not failures, data

def print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('project_root')
    args=ap.parse_args(); print_json(inspect(Path(args.project_root).resolve())); return 0
if __name__=='__main__': raise SystemExit(main())
