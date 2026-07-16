#!/usr/bin/env bash
# 可选：用 PyInstaller 打后端二进制（不装 pyinstaller 时跳过）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"
OUT="$ROOT/backend-dist"
mkdir -p "$OUT"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "[build-backend] 未安装 pyinstaller，跳过二进制打包。"
  echo "  安装: pip install pyinstaller"
  echo "  生产模式将回退到系统 python3 + run-backend.py"
  exit 0
fi

cd "$REPO"
pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name medora-backend \
  --distpath "$OUT" \
  --workpath "$OUT/build" \
  --specpath "$OUT" \
  --paths "$REPO" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan \
  --hidden-import uvicorn.lifespan.on \
  "$ROOT/scripts/run-backend.py"

echo "[build-backend] 输出: $OUT/medora-backend"
