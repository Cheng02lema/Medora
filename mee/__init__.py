from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTFORGE_DIR = Path(__file__).resolve().parent / "resources" / "prompt_engineering"
if PROMPTFORGE_DIR.exists():
    dir_str = str(PROMPTFORGE_DIR)
    if dir_str not in sys.path:
        sys.path.append(dir_str)

__all__ = ["PROJECT_ROOT"]
