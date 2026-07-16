from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape


class TemplateRenderer:
    def __init__(self, template_dir: str) -> None:
        loader = FileSystemLoader(str(Path(template_dir)))
        self.env = Environment(
            loader=loader,
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        template = self.env.get_template(template_name)
        return template.render(**context)
