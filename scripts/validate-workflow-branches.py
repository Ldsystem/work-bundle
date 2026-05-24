from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def out(data): print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
def text(path): return Path(path).read_text(encoding='utf-8') if Path(path).exists() else ''
def exists(path): return Path(path).exists()

BRANCHES=['success','blocked','invalid','missing-context','repair-needed','no-op-idempotent','read-only-diagnosis']
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('project_root')
    args=ap.parse_args(); pr=Path(args.project_root).resolve(); ev=pr/'.work-bundle/orchestration/reviews/branch-validation/evidence.json'
    if not ev.exists():
        out({'status':'issues-found','failures':['missing_branch_evidence'],'required_branches':BRANCHES}); return 1
    data=json.loads(ev.read_text(encoding='utf-8'))
    seen={x.get('branch') for x in data.get('evidence',[])}
    missing=[b for b in BRANCHES if b not in seen]
    out({'status':'passed' if not missing else 'issues-found','missing':missing,'evidence':str(ev)}); return 0 if not missing else 1
if __name__=='__main__': raise SystemExit(main())
