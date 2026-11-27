"""跨工作区启动器：从任意 cwd 调用同一套引擎和台账。

用法：
    python d:\\workfile\\2026\\brain_api\\wq.py status
    python d:\\workfile\\2026\\brain_api\\wq.py precheck --batch b1
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
