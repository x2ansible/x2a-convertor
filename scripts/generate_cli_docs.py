#!/usr/bin/env python3
"""Generate CLI documentation from Click commands."""

import sys
from pathlib import Path

import click

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import cli  # noqa: E402


def generate_cli_docs(output_file="docs/cli-reference.md"):
    """Generate markdown documentation from Click CLI commands."""

    lines = []

    # Add header
    lines.append("---")
    lines.append("layout: default")
    lines.append("title: CLI Reference")
    lines.append("nav_order: 5")
    lines.append("---")
    lines.append("")
    lines.append("# CLI Reference")
    lines.append("{: .no_toc }")
    lines.append("")
    lines.append("## Table of contents")
    lines.append("{: .no_toc .text-delta }")
    lines.append("")
    lines.append("<style>")
    lines.append(".toc-h2-only ul {")
    lines.append("    display: none;")
    lines.append("}")
    lines.append("</style>")
    lines.append("")
    lines.append("* TOC")
    lines.append("{:toc .toc-h2-only}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Complete command-line interface reference for X2A Convertor.")
    lines.append("")

    # Add main CLI help
    ctx = click.Context(cli)
    lines.append("## Main Command")
    lines.append("")
    lines.append("```")
    lines.append(f"{cli.get_help(ctx)}")
    lines.append("```")
    lines.append("")

    # Add each subcommand
    for cmd_name in sorted(cli.commands.keys()):
        cmd = cli.commands[cmd_name]
        ctx = click.Context(cmd, info_name=cmd_name, parent=click.Context(cli))

        lines.append(f"## {cmd_name}")
        lines.append("")

        # Add command help
        if cmd.help:
            lines.append(cmd.help)
            lines.append("")

        # Add usage
        lines.append("### Usage")
        lines.append("")
        lines.append("```bash")

        # Build argument list safely
        arg_parts: list[str] = []
        for p in cmd.params:
            if isinstance(p, click.Argument) and p.name:
                name_upper = str(p.name.upper())
                if p.required:
                    arg_parts.append(name_upper)
                else:
                    arg_parts.append(f"[{name_upper}]")

        args_str = " ".join(arg_parts)
        lines.append(f"uv run app.py {cmd_name} [OPTIONS] {args_str}".strip())
        lines.append("```")
        lines.append("")

        # Add arguments
        arguments = [p for p in cmd.params if isinstance(p, click.Argument)]
        if arguments:
            lines.append("### Arguments")
            lines.append("")
            for arg in arguments:
                if arg.name:
                    lines.append(f"- `{arg.name.upper()}`")
            lines.append("")

        # Add options
        options = [p for p in cmd.params if isinstance(p, click.Option)]
        if options:
            lines.append("### Options")
            lines.append("")
            for opt in options:
                opt_str = ", ".join(opt.opts)
                default = (
                    f" (default: {opt.default})"
                    if opt.default and not opt.is_flag
                    else ""
                )
                required = " **[required]**" if opt.required else ""
                lines.append(f"- `{opt_str}`{required}{default}")
                if opt.help:
                    lines.append(f"  {opt.help}")
                lines.append("")

        # Add full help output
        lines.append("### Full Help")
        lines.append("")
        lines.append("```")
        lines.append(cmd.get_help(ctx))
        lines.append("```")
        lines.append("")

    # Write to file relative to project root
    output_path = project_root / output_file
    output_path.write_text("\n".join(lines))

    print(f"CLI documentation generated at: {output_file}")


if __name__ == "__main__":
    generate_cli_docs()
