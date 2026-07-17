"""Clarinora 后端 —— FastAPI 服务 + 内置 engine 纯逻辑。"""

from pathlib import Path
import sys

# antigravity/ 包根
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 仓库根（数据提取/ 或打包 resources/）
DATA_ROOT = PROJECT_ROOT.parent

for p in (str(DATA_ROOT), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# engine 内 promptforge 以顶层包导入
_engine = PROJECT_ROOT / "engine"
if str(_engine) not in sys.path:
    sys.path.insert(0, str(_engine))

WORKSPACE = PROJECT_ROOT / "workspace"

__all__ = ["PROJECT_ROOT", "DATA_ROOT", "WORKSPACE"]
