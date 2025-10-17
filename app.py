#!/usr/bin/env python3

import click
import logging
import os
import sys
from dotenv import load_dotenv

from langchain.globals import set_debug
from src.init import init_project
from src.exporters.migrate import migrate_module
from src.validate import validate_module
from src.inputs.analyze import analyze_project


def setup_logging() -> None:
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    langchain_debug = os.environ.get("LANGCHAIN_DEBUG", "FALSE").upper()
    logging.basicConfig(stream=sys.stderr, level=log_level)
    if langchain_debug == "TRUE":
        set_debug(True)


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx) -> None:
    """X2Ansible - Infrastructure Migration Tool"""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument("user_requirements")
@click.option("--source-dir", default=".", help="Source directory to analyze")
def init(user_requirements, source_dir) -> None:
    """Initialize project with interactive message"""
    init_project(user_requirements=user_requirements, source_dir=source_dir)


@cli.command()
@click.argument("user_requirements")
@click.option("--source-dir", default=".", help="Source directory to analyze")
def analyze(user_requirements, source_dir) -> None:
    """Perform detailed analysis and create module migration plans"""
    analyze_project(user_requirements, source_dir)


@cli.command()
@click.argument("user_requirements")
@click.option("--source-dir", default=".", help="Source directory to migrate")
@click.option(
    "--source-technology",
    default="Chef",
    help="Source technology to migrate from [Chef, Puppet, Salt]",
)
@click.option(
    "--module-migration-plan",
    help="Module migration plan file produced by the analyze command. Must be in the format: migration-plan-<module_name>.md. Path is relative to the --source-dir. Example: migration-plan-nginx.md",
)
@click.option(
    "--high-level-migration-plan",
    help="High level migration plan file produced by the init command. Path is relative to the --source-dir. Example: migration-plan.md",
)
def migrate(
    user_requirements,
    source_technology,
    source_dir,
    module_migration_plan,
    high_level_migration_plan,
) -> None:
    """Based on the migration plan produced within analysis, migrate the project"""
    migrate_module(
        user_requirements,
        source_technology,
        module_migration_plan,
        high_level_migration_plan,
        source_dir=source_dir,
    )


@cli.command()
@click.argument("module_name")
def validate(module_name) -> None:
    """Validate migrated module against original configuration"""
    validate_module(module_name)


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    cli()
