#!/usr/bin/env python3
"""Generate usage documentation for native and Docker workflows.

Content is read from usage_docs_content.yaml - edit that file to update docs.
"""

from pathlib import Path

import yaml

# Project root for resolving output paths
PROJECT_ROOT = Path(__file__).parent.parent
CONTENT_FILE = Path(__file__).parent / "usage_docs_content.yaml"


def load_content() -> dict:
    """Load content from YAML file."""
    return yaml.safe_load(CONTENT_FILE.read_text())


def docker_command(
    command: str,
    env_vars: list[str],
    image: str,
    volume_mount: str,
) -> str:
    """Build a podman run command with the given env vars."""
    env_lines = "\n".join(f"  -e {var} \\" for var in env_vars)
    return f"""\
podman run --rm -ti \\
  -v {volume_mount} \\
{env_lines}
  {image} \\
  {command}"""


def generate_usage_doc(content: dict):
    """Generate local usage documentation."""
    shared = content["shared"]
    config = content["local"]

    lines = []

    # Add header
    lines.append("---")
    lines.append("layout: default")
    lines.append(f"title: {config['title']}")
    lines.append("parent: Getting Started")
    lines.append(f"nav_order: {config['nav_order']}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {config['title']}")
    lines.append("")
    lines.append(config["intro"])
    lines.append("")
    lines.append(shared["quick_reference"].rstrip())
    lines.append("")
    lines.append(shared["requirements_intro"].rstrip())

    if config.get("include_env_exports"):
        lines.append(shared["env_exports"].rstrip())

    lines.append("")

    # Init section
    lines.append("## Initialization")
    lines.append("")
    lines.append(
        "The first thing we need to do is create the migration-plan.md "
        "file which will be used as a reference file:"
    )
    lines.append("")
    lines.append("```bash")
    lines.append(config["commands"]["init"])
    lines.append("```")
    lines.append("")
    lines.append(shared["descriptions"]["init"])
    lines.append("")

    # Analyze section
    lines.append("## Analyze:")
    lines.append("")
    lines.append("```bash")
    lines.append(config["commands"]["analyze"])
    lines.append("```")
    lines.append("")
    lines.append(shared["descriptions"]["analyze"])
    lines.append("")

    # Migrate section
    lines.append("## Migrate")
    lines.append("")
    lines.append("```bash")
    lines.append(config["commands"]["migrate"])
    lines.append("```")
    lines.append("")
    lines.append(shared["descriptions"]["migrate"])
    lines.append("")

    # Publish section
    lines.append("## Publish")
    lines.append("")
    lines.append("```bash")
    lines.append(config["commands"]["publish"])
    lines.append("```")
    lines.append("")
    lines.append(shared["descriptions"]["publish"])
    lines.append(shared["publish_output_paths"].rstrip())

    if config.get("include_notes"):
        lines.append("")
        lines.append(shared["notes_section"].rstrip())

    # Write to file relative to project root
    output_path = PROJECT_ROOT / config["output_file"]
    output_path.write_text("\n".join(lines) + "\n")

    print(f"Usage documentation generated at: {config['output_file']}")


def generate_docker_usage_doc(content: dict):
    """Generate Docker usage documentation."""
    shared = content["shared"]
    config = content["docker"]

    lines = []

    # Add header
    lines.append("---")
    lines.append("layout: default")
    lines.append(f"title: {config['title']}")
    lines.append("parent: Getting Started")
    lines.append(f"nav_order: {config['nav_order']}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {config['title']}")
    lines.append("")
    lines.append(config["intro"])
    lines.append("")
    lines.append(shared["quick_reference"].rstrip())
    lines.append("")
    lines.append(shared["requirements_intro"].rstrip())

    if config.get("include_env_exports"):
        lines.append(shared["env_exports"].rstrip())

    lines.append("")

    # Helper to get env vars for a command
    def get_env_vars(cmd_config: dict) -> list[str]:
        env_type = cmd_config["env_type"]
        return config["env_vars"][env_type]

    # Helper to wrap command in podman
    def wrap_cmd(cmd_config: dict) -> str:
        return docker_command(
            cmd_config["cmd"],
            get_env_vars(cmd_config),
            config["container"]["image"],
            config["container"]["volume_mount"],
        )

    # Init section
    lines.append("## Initialization")
    lines.append("")
    lines.append(
        "The first thing we need to do is create the migration-plan.md "
        "file which will be used as a reference file:"
    )
    lines.append("")
    lines.append("```bash")
    lines.append(wrap_cmd(config["commands"]["init"]))
    lines.append("```")
    lines.append("")
    lines.append(shared["descriptions"]["init"])
    lines.append("")

    # Analyze section
    lines.append("## Analyze:")
    lines.append("")
    lines.append("```bash")
    lines.append(wrap_cmd(config["commands"]["analyze"]))
    lines.append("```")
    lines.append("")
    lines.append(shared["descriptions"]["analyze"])
    lines.append("")

    # Migrate section
    lines.append("## Migrate")
    lines.append("")
    lines.append("```bash")
    lines.append(wrap_cmd(config["commands"]["migrate"]))
    lines.append("```")
    lines.append("")
    lines.append(shared["descriptions"]["migrate"])
    lines.append("")

    # Publish section
    lines.append("## Publish")
    lines.append("")
    lines.append("```bash")
    lines.append(wrap_cmd(config["commands"]["publish"]))
    lines.append("```")
    lines.append("")
    lines.append(shared["descriptions"]["publish"])
    lines.append(shared["publish_output_paths"].rstrip())

    if config.get("include_notes"):
        lines.append("")
        lines.append(shared["notes_section"].rstrip())

    # Write to file relative to project root
    output_path = PROJECT_ROOT / config["output_file"]
    output_path.write_text("\n".join(lines) + "\n")

    print(f"Docker usage documentation generated at: {config['output_file']}")


def generate_usage_docs():
    """Generate all usage documentation files."""
    content = load_content()
    generate_usage_doc(content)
    generate_docker_usage_doc(content)


if __name__ == "__main__":
    generate_usage_docs()
