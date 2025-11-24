"""Template loader for publisher templates."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

base_path = Path(__file__).parent.parent.parent / "templates" / "publishers"
jinja_env = Environment(loader=FileSystemLoader(base_path))


def get_template(template_name: str):
    """Load a Jinja2 template from the publishers templates directory.

    Args:
        template_name: Name of the template file (without .j2 extension)

    Returns:
        Jinja2 Template object

    Raises:
        FileNotFoundError: If template file doesn't exist
    """
    template_file = f"{template_name}.j2"
    return jinja_env.get_template(template_file)
