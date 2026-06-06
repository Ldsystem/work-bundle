from core import *

def cmd_init(args: argparse.Namespace) -> None:
    init_dirs(args)
    print(str(orchestration_root(args)))

