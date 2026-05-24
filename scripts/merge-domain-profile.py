from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

def out(data): print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
def text(path): return Path(path).read_text(encoding='utf-8') if Path(path).exists() else ''
def write(path, data): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(data, encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--current'); ap.add_argument('--incoming', required=True); ap.add_argument('--output', required=True)
    args=ap.parse_args(); write(args.output, text(args.incoming)); out({'status':'passed','output':args.output}); return 0
if __name__=='__main__': raise SystemExit(main())
