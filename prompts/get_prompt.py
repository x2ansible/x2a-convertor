from pathlib import Path
from jinja2 import Environment, FileSystemLoader

base_path = Path(__file__).parent
jinja_env = Environment(loader=FileSystemLoader(base_path))


class JinjaTemplate:
    def __init__(self, template):
        self.template = template

    def format(self, **kwargs):
        return self.template.render(**kwargs)


def get_prompt(prompt_name: str) -> str | JinjaTemplate:
    j2_file = base_path / f"{prompt_name}.j2"
    if j2_file.exists():
        template = jinja_env.get_template(f"{prompt_name}.j2")
        return JinjaTemplate(template)

    md_file = base_path / f"{prompt_name}.md"
    return md_file.read_text(encoding="utf-8")
