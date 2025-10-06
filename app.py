#!/usr/bin/env python3

import click
import logging
import os
import sys
from dotenv import load_dotenv

from langchain.globals import set_debug
from src.init import init_project
from src.exporters.migrate import migrate_component
from src.validate import validate_component
from src.inputs.analyze import analyze_project


def setup_logging():
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(stream=sys.stderr, level=log_level)
    if log_level == "DEBUG":
        set_debug(True)


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """X2Ansible - Infrastructure Migration Tool"""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument("user_requirements")
@click.option("--source-dir", default=".", help="Source directory to analyze")
def init(user_requirements, source_dir):
    """Initialize project with interactive message"""
    init_project(user_requirements=user_requirements, source_dir=source_dir)


@cli.command()
@click.argument("user_requirements")
@click.option("--source-dir", default=".", help="Source directory to analyze")
def analyze(user_requirements, source_dir):
    """Perform detailed analysis and create component migration plans"""
    analyze_project(user_requirements, source_dir)


@cli.command()
@click.argument("user_requirements")
@click.option("--source-dir", default=".", help="Source directory to migrate")
@click.option(
    "--component",
    default="default",
    help='Component from the source directory to migrate, see output of the analyze command. If not provided: "default"',
)
def migrate(user_requirements, component, source_dir):
    """Based on the migration plan produced within analysis, migrate the project"""
    migrate_component(
        user_requirements, component_name=component, source_dir=source_dir
    )


@cli.command()
@click.argument("component_name")
def validate(component_name):
    """Validate migrated component against original configuration"""
    validate_component(component_name)


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    cli()
