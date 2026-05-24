from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

def out(data): print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
def text(path): return Path(path).read_text(encoding='utf-8') if Path(path).exists() else ''
def write(path, data): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(data, encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('profile')
    args=ap.parse_args(); p=Path(args.profile); s=text(p)
    required=['id:','status:','industry:','business_context:','source_knowledge:','role_positioning:','warnings:']
    failures=[r for r in required if r not in s]
    if len(s.splitlines())>120: failures.append('prose_heavy')
    out({'path':str(p),'status':'passed' if not failures else 'issues-found','failures':failures,'line_count':len(s.splitlines())})
    return 0 if not failures else 1
if __name__=='__main__': raise SystemExit(main())
