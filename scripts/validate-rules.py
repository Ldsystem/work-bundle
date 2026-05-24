from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

def out(data): print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
def text(path): return Path(path).read_text(encoding='utf-8') if Path(path).exists() else ''
def write(path, data): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(data, encoding='utf-8')

REQ=['id:','status:','scope: work-bundle','enable_when:','severity:','required_behavior:','prohibited_behavior:','validation:','source_authority:']
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('rules_root')
    args=ap.parse_args(); root=Path(args.rules_root); failures=[]
    if list(root.glob('*.mdc')): failures.append('generated_mdc_present')
    for p in root.glob('*.yaml'):
        if p.name in {'index.yaml','contract.yaml'}: continue
        s=text(p)
        for req in REQ:
            if req not in s: failures.append(f'{p.name}:{req}')
        if len(s.splitlines())>80: failures.append(f'{p.name}:prose_heavy')
    out({'status':'passed' if not failures else 'issues-found','failures':failures}); return 0 if not failures else 1
if __name__=='__main__': raise SystemExit(main())
