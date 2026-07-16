import glob
import os
from pathlib import Path
from typing import List, Tuple


def delete_matching_files(folder_path: str, pattern: str = "*右表格_0.md", dry_run: bool = False) -> Tuple[int, List[str]]:
    folder = Path(folder_path)
    if not folder.exists():
        return 0, []
    glob_pattern = str(folder / "**" / pattern)
    files = glob.glob(glob_pattern, recursive=True)
    if dry_run:
        return len(files), files
    deleted = 0
    for path in files:
        try:
            os.remove(path)
            deleted += 1
        except OSError:
            pass
    return deleted, files


__all__ = ["delete_matching_files"]
