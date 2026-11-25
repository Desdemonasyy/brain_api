"""打印指定 alpha 的完整检查明细。用法：python _chk.py <id1> <id2> ..."""
import sys

import brain

s = brain.load()
for aid in sys.argv[1:]:
    brain.report(s, aid)
    print()
