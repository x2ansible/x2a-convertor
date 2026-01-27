#!/usr/bin/env python3

import os
import sys
from functools import wraps

import click
from dotenv import load_dotenv

from src.error_details import get_error_human_message
from src.exporters.migrate import migrate_module
from src.init import init_project
from src.inputs.analyze import analyze_project
from src.publishers.publish import publish_role
from src.utils.logging import get_logger, setup_logging
from src.validate import validate_module

logger = get_logger(__name__)


def change_dir_callback(ctx, param, value):
    """Callback to change directory when source-dir is provided"""
    if value:
        os.chdir(value)
    return value


def handle_exceptions(func):
    """
    Decorator to catch and log exceptions with formatted output.

    Provides nice error messages for all know errors and other exceptions,
    logging them properly before exiting.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            human_message = get_error_human_message(e)
            error_label = click.style("Error: ", fg="red", bold=True)
            click.echo(
                "\n\n" + error_label + human_message,
                err=True,
            )
            sys.exit(1)

    return wrapper


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
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Skip migration plan generation if migration-plan.md exists, only regenerate metadata",
)
@handle_exceptions
def init(user_requirements, source_dir, refresh) -> None:
    """Initialize project with interactive message"""
    result = init_project(
        user_requirements=user_requirements, source_dir=source_dir, refresh=refresh
    )

    # User-facing success messages
    click.echo("\nInit workflow completed successfully!")
    click.echo(f"Migration plan: {result.migration_plan_path}")
    click.echo(
        f"Metadata file: .x2ansible-metadata.json ({len(result.metadata_items)} modules)"
    )


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
@handle_exceptions
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
@handle_exceptions
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
@handle_exceptions
def validate(module_name) -> None:
    """Validate migrated module against original configuration"""
    validate_module(module_name)


@cli.command()
@click.argument("module_names", nargs=-1, required=True)
@click.option(
    "--source-paths",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    required=True,
    help=(
        "Path(s) to the migrated Ansible role directory(ies). "
        "Can be specified multiple times. "
        "Example: --source-paths ./ansible/roles/role1 "
        "--source-paths ./ansible/roles/role2"
    ),
)
@click.option(
    "--base-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help=(
        "Base path for constructing deployment path. "
        "If not provided, derived from first source-paths "
        "(parent of ansible/roles)."
    ),
)
@click.option(
    "--github-owner",
    help=(
        "GitHub user or organization name where the repository "
        "will be created (required if not using --skip-git)"
    ),
)
@click.option(
    "--github-branch",
    default="main",
    help="GitHub branch to push to (default: main, ignored if --skip-git)",
)
@click.option(
    "--skip-git",
    is_flag=True,
    default=False,
    help="Skip git steps (create repo, commit, push). "
    "Files will be created in <base-path>/ansible/deployments/ only.",
)
@click.option(
    "--collections-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Path to YAML/JSON file containing collections list. "
        'Format: [{"name": "collection.name", "version": "1.0.0"}]'
    ),
)
@click.option(
    "--inventory-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Path to YAML/JSON file containing inventory structure. "
        'Format: {"all": {"children": {...}}}'
    ),
)
@handle_exceptions
def publish(
    module_names,
    source_paths,
    base_path,
    github_owner,
    github_branch,
    skip_git,
    collections_file,
    inventory_file,
) -> None:
    """Publish migrated Ansible roles to Ansible Automation Platform
    wrap the roles in an Ansible Project format,
    push the project to git, and sync to AAP.

    Creates a new GitOps repository and pushes the deployment to it.
    For single role: creates deployment at
    `<base-path>/ansible/deployments/{module_name}`.
    For multiple roles: creates a consolidated project at
    `<base-path>/ansible/deployments/ansible-project`.
    """
    if not skip_git and not github_owner:
        raise click.BadParameter(
            "--github-owner is required when not using --skip-git",
            param_hint="--github-owner",
        )

    publish_role(
        module_names,
        source_paths,
        github_owner or "",
        github_branch or "main",
        base_path=base_path,
        skip_git=skip_git,
        collections_file=collections_file,
        inventory_file=inventory_file,
    )


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    cli()
