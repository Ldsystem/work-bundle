from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

def out(data): print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
def text(path): return Path(path).read_text(encoding='utf-8') if Path(path).exists() else ''
def write(path, data): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(data, encoding='utf-8')

def norm(t): return re.sub(r'[^a-z0-9]+','-',t.lower()).strip('-') or 'unknown-skill'
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('skill_file')
    args=ap.parse_args(); p=Path(args.skill_file); s=text(p); name=p.parent.name
    m=re.search(r'^name:\s*(.+)$', s, re.M); name=m.group(1).strip() if m else name
    out({'skill_id':norm(name),'source':str(p),'capability_summary':' '.join(s.split())[:240],'warnings':[]}); return 0
if __name__=='__main__': raise SystemExit(main())
