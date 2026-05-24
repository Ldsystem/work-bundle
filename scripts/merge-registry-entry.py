from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

def out(data): print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
def text(path): return Path(path).read_text(encoding='utf-8') if Path(path).exists() else ''
def write(path, data): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(data, encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--registry', required=True); ap.add_argument('--entry', required=True); ap.add_argument('--confirmed', action='store_true')
    args=ap.parse_args()
    if not args.confirmed: out({'status':'blocked','blocker':'confirmation-required'}); return 2
    reg=Path(args.registry).expanduser(); existing=text(reg); write(reg, (existing.rstrip()+'\n'+text(args.entry)).lstrip()); out({'status':'passed','registry':str(reg)}); return 0
if __name__=='__main__': raise SystemExit(main())
