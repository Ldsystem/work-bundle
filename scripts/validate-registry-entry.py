from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

def out(data): print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
def text(path): return Path(path).read_text(encoding='utf-8') if Path(path).exists() else ''
def write(path, data): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(data, encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('entry')
    args=ap.parse_args(); s=text(args.entry); failures=[t for t in ['source:','mode:','priority:','used_by:','stages:','allowed_outputs:','validation:','fallback:'] if t not in s]
    out({'status':'passed' if not failures else 'issues-found','failures':failures}); return 0 if not failures else 1
if __name__=='__main__': raise SystemExit(main())
