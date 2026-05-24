from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def out(data): print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
def text(path): return Path(path).read_text(encoding='utf-8') if Path(path).exists() else ''
def exists(path): return Path(path).exists()

def inspect(project_root: Path):
    wb=project_root/'.work-bundle'
    rules=project_root/'references/rules'
    return {
      'project_root': str(project_root),
      'project_gitignore': (project_root/'.gitignore').exists(),
      'agents_md': (project_root/'AGENTS.md').exists(),
      'work_bundle': wb.exists(),
      'work_bundle_gitignore': (wb/'.gitignore').exists(),
      'repository_binding': (wb/'orchestration/bootstrap/repository-binding.md').exists(),
      'agent_bootstrap': (wb/'orchestration/bootstrap/agent-bootstrap.md').exists(),
      'project_domain_profile': (wb/'orchestration/bootstrap/project-domain-profile.yaml').exists(),
      'rules_root': rules.exists(),
      'rule_files': len(list(rules.glob('*.yaml'))) if rules.exists() else 0,
      'mdc_rules': [str(p) for p in rules.glob('*.mdc')] if rules.exists() else [],
    }
def status(data):
    req=['project_gitignore','agents_md','work_bundle','work_bundle_gitignore','repository_binding','agent_bootstrap','project_domain_profile','rules_root']
    failures=[k for k in req if not data.get(k)]
    if data.get('mdc_rules'): failures.append('mdc_rules_present')
    return failures

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('project_root')
    args=ap.parse_args(); data=inspect(Path(args.project_root).resolve()); failures=status(data)
    out({'status':'passed' if not failures else 'issues-found','failures':failures,'files_changed':'none','data':data}); return 0 if not failures else 1
if __name__=='__main__': raise SystemExit(main())
