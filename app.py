#!/usr/bin/env python3

import os

import click
from dotenv import load_dotenv

from src.exporters.migrate import migrate_module
from src.init import init_project
from src.inputs.analyze import analyze_project
from src.publishers.publish import publish_role
from src.utils.logging import setup_logging
from src.validate import validate_module


def change_dir_callback(ctx, param, value):
    """Callback to change directory when source-dir is provided"""
    if value:
        os.chdir(value)
    return value


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx) -> None:
    """X2Ansible - Infrastructure Migration Tool"""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument("user_requirements")
@click.option(
    "--source-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    callback=change_dir_callback,
    is_eager=True,
    help="Source directory to analyze",
)
def init(user_requirements, source_dir) -> None:
    """Initialize project with interactive message"""
    init_project(user_requirements=user_requirements, source_dir=source_dir)


@cli.command()
@click.argument("user_requirements")
@click.option(
    "--source-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    callback=change_dir_callback,
    is_eager=True,
    help="Source directory to analyze",
)
def analyze(user_requirements, source_dir) -> None:
    """Perform detailed analysis and create module migration plans"""
    analyze_project(user_requirements, source_dir)


@cli.command()
@click.argument("user_requirements")
@click.option(
    "--source-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    callback=change_dir_callback,
    is_eager=True,
    help="Source directory to migrate",
)
@click.option(
    "--source-technology",
    default="Chef",
    help="Source technology to migrate from [Chef, Puppet, Salt]",
)
@click.option(
    "--module-migration-plan",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Module migration plan file produced by the analyze command. "
        "Must be in the format: migration-plan-<module_name>.md. "
        "Path is relative to the --source-dir. "
        "Example: migration-plan-nginx.md"
    ),
)
@click.option(
    "--high-level-migration-plan",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "High level migration plan file produced by the init command. "
        "Path is relative to the --source-dir. "
        "Example: migration-plan.md"
    ),
)
def migrate(
    user_requirements,
    source_technology,
    source_dir,
    module_migration_plan,
    high_level_migration_plan,
) -> None:
    """Migrate project based on migration plan from analysis"""
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


@cli.command()
@click.argument("module_name")
@click.option(
    "--source-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    required=True,
    help=(
        "Path to the migrated Ansible role directory (e.g., ./ansible/roles/my_role)"
    ),
)
@click.option(
    "--base-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Base path for constructing deployment path. "
    "If not provided, derived from source-path (parent of ansible/roles).",
)
@click.option(
    "--github-owner",
    required=True,
    help="GitHub user or organization name where the repository will be created",
)
@click.option(
    "--github-branch",
    default="main",
    help="GitHub branch to push to (default: main)",
)
@click.option(
    "--skip-git",
    is_flag=True,
    default=False,
    help="Skip git steps (create repo, commit, push). "
    "Files will be created in <base-path>/ansible/deployments/{module_name}/ only.",
)
def publish(
    module_name,
    source_path,
    base_path,
    github_owner,
    github_branch,
    skip_git,
) -> None:
    """Publish migrated Ansible role to GitHub using GitOps approach.

    Creates a new GitOps repository and pushes the deployment to it.
    Takes role from <base-path>/ansible/roles/{module_name} and creates
    deployment at <base-path>/ansible/deployments/{module_name}.
    """
    publish_role(
        module_name,
        source_path,
        github_owner,
        github_branch,
        base_path=base_path,
        skip_git=skip_git,
    )


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    cli()
