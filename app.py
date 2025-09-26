#!/usr/bin/env python3

import click
from src.init import init_project
from src.migrate import migrate_component
from src.validate import validate_component
from src.inputs.analyze import analyze_project


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """X2Ansible - Infrastructure Migration Tool"""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument('message')
def init(message):
    """Initialize project with interactive message"""
    init_project(message)


@cli.command()
def analyze():
    """Perform detailed analysis and create component migration plans"""
    analyze_project()


@cli.command()
@click.argument('component_name')
def migrate(component_name):
    """Migrate specific component to Ansible (e.g., 'postgres', 'nginx')"""
    migrate_component(component_name)


@cli.command()
@click.argument('component_name')
def validate(component_name):
    """Validate migrated component against original configuration"""
    validate_component(component_name)


if __name__ == "__main__":
    cli()