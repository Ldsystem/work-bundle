from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

def out(data): print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
def text(path): return Path(path).read_text(encoding='utf-8') if Path(path).exists() else ''
def write(path, data): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(data, encoding='utf-8')

RULES=['repository-boundary','knowledge-boundary','orchestration-boundary','lifecycle-authority','retrieval-gateway','role-context','skill-registry','domain-profile','execution-boundary','handoff-boundary','review-archive-boundary','doctor-readonly','runtime-artifact-format','security-exclusion']
def rule(name):
    return ('id: rule-work-bundle-{0}\nstatus: current\nscope: work-bundle\napplies_to: {{paths: [.work-bundle/**], skills: [], artifacts: []}}\nenable_when: [v4 work-bundle operation requires {0}]\nseverity: must\nrule: {0} rule applies to v4 work-bundle operations.\nrequired_behavior: [follow source authority, keep runtime files compact]\nprohibited_behavior: [do not generate .mdc files, do not include raw logs or secrets]\nvalidation: [required fields exist, scope is work-bundle]\nsource_authority: [.work-bundle/orchestration/spec/active/spec-process-v4-project-local-agent-operating-system.md]\ndeprecated_sources: []\n').format(name)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('rules_root')
    args=ap.parse_args(); root=Path(args.rules_root); root.mkdir(parents=True, exist_ok=True)
    for r in RULES: write(root/f'{r}.yaml', rule(r))
    write(root/'index.yaml', 'id: work-bundle-rule-index\nstatus: current\nrules:\n' + ''.join([f'  - {r}.yaml\n' for r in RULES]))
    out({'status':'passed','rules':RULES}); return 0
if __name__=='__main__': raise SystemExit(main())
