from __future__ import annotations

import argparse
from pathlib import Path

from mee.core.theme_manager import PALETTES

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "components"
THEMES = ROOT / "themes"
DIST = ROOT / "dist"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_stylesheet(theme: str) -> str:
    palette = PALETTES[theme]
    parts = [read_text(p) for p in sorted(COMPONENTS.glob("*.qss"))]
    parts.append(read_text(THEMES / f"{theme}.qss"))
    css = "\n".join(parts)
    for token, value in palette.items():
        css = css.replace(token, value)
    return css


def build(theme: str):
    DIST.mkdir(exist_ok=True)
    output = DIST / f"medflow_{theme}.qss"
    output.write_text(build_stylesheet(theme), encoding="utf-8")
    print(f"✓ wrote {output}")


def main():
    parser = argparse.ArgumentParser(description="Assemble MedFlow QSS from components")
    parser.add_argument("theme", nargs="?", choices=PALETTES.keys(), help="Theme to build")
    args = parser.parse_args()
    if args.theme:
        build(args.theme)
    else:
        for theme in PALETTES.keys():
            build(theme)


if __name__ == "__main__":
    main()
