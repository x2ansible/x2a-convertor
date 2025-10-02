#!/usr/bin/env python3

import click
import logging
import os
import sys
from dotenv import load_dotenv

from langchain.globals import set_debug
from src.init import init_project
from src.migrate import migrate_component
from src.model import list_models
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
def analyze():
    """Perform detailed analysis and create component migration plans"""
    analyze_project()


@cli.command()
@click.argument("component_name")
def migrate(component_name):
    """Migrate specific component to Ansible (e.g., 'postgres', 'nginx')"""
    migrate_component(component_name)


@cli.command()
@click.argument("component_name")
def validate(component_name):
    """Validate migrated component against original configuration"""
    validate_component(component_name)


@cli.command()
def models():
    """List all models available at the OPENAI_API_BASE endpoint, if set"""
    list_models()


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    cli()
