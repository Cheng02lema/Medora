#!/usr/bin/env python3
"""Medora 后端启动入口（生产/开发通用）。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _bootstrap_paths() -> Path:
    """把含 antigravity 包的根目录加入 sys.path。"""
    here = Path(__file__).resolve()
    candidates = [
        here.parent,  # resources/ 或 scripts/
        here.parent.parent,  # antigravity/
        here.parent.parent.parent,  # 数据提取/ 或 resources 上级
    ]
    root = None
    for c in candidates:
        if (c / "antigravity").is_dir() and (c / "antigravity" / "backend").is_dir():
            root = c
            break
        # 打包后可能是 resources/antigravity/...
        if c.name == "antigravity" and (c / "backend").is_dir():
            root = c.parent
            break
        if (c / "backend").is_dir() and (c / "backend" / "app.py").exists() and (c / "engine").is_dir():
            # antigravity 自身作为 cwd
            root = c.parent if c.name == "antigravity" else c
            if not (root / "antigravity").is_dir() and c.name == "antigravity":
                # sys.path 需要能 import antigravity → root 是 parent
                root = c.parent
            break
    if root is None:
        root = here.parent.parent.parent if here.parent.name == "scripts" else here.parent

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # 开发时 antigravity 在 root/antigravity
    antigravity_dir = root / "antigravity"
    if antigravity_dir.is_dir() and root_str not in sys.path:
        sys.path.insert(0, root_str)

    os.environ.setdefault("MEDORA_ROOT", root_str)
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description="Medora Backend")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MEDORA_PORT", os.environ.get("MEDFLOW_PORT", "8765"))))
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    _bootstrap_paths()

    import uvicorn

    uvicorn.run(
        "antigravity.backend.app:app",
        host=args.host,
        port=args.port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
