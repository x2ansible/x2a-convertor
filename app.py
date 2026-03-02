#!/usr/bin/env python3

import os
import sys
from functools import wraps

import click
from dotenv import load_dotenv

from src.const import METADATA_FILENAME
from src.error_details import get_error_human_message
from src.exporters.migrate import migrate_module
from src.init import init_project
from src.inputs.analyze import analyze_project
from src.publishers.publish import publish_aap, publish_project
from src.report import report_artifacts
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
        f"Metadata file: {METADATA_FILENAME} with {len(result.metadata_items)} modules"
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


@cli.command("publish-project")
@click.argument("project_id")
@click.argument("module_name")
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
def publish_project_cmd(
    project_id,
    module_name,
    collections_file,
    inventory_file,
) -> None:
    """Create or append to an Ansible project for a migrated module.

    PROJECT_ID is the migration project ID.
    MODULE_NAME is the module/role to add.

    On the first module, creates the full skeleton (ansible.cfg, collections,
    inventory). On subsequent modules, appends the role and playbook.

    Role names are sanitized to comply with Ansible standards: hyphens are
    replaced with underscores (e.g., fastapi-tutorial becomes fastapi_tutorial).
    """
    project_dir = publish_project(
        project_id=project_id,
        module_name=module_name,
        collections_file=collections_file,
        inventory_file=inventory_file,
    )
    click.echo(f"\nProject created at: {project_dir}")


@cli.command("publish-aap")
@click.option(
    "--target-repo",
    required=True,
    help="Git repository URL for the AAP project (e.g., https://github.com/org/repo.git).",
)
@click.option(
    "--target-branch",
    required=True,
    help="Git branch for the AAP project.",
)
@click.option(
    "--project-id",
    required=True,
    help="Migration project ID, used for AAP project naming and subdirectory reference.",
)
@handle_exceptions
def publish_aap_cmd(target_repo, target_branch, project_id) -> None:
    """Sync a git repository to Ansible Automation Platform.

    Creates or updates an AAP Project pointing to the given repository URL
    and branch, then triggers a project sync.

    Requires AAP environment variables to be configured
    (AAP_CONTROLLER_URL, AAP_ORG_NAME, and authentication credentials).
    """
    result = publish_aap(
        target_repo=target_repo, target_branch=target_branch, project_id=project_id
    )
    click.echo(f"\nAAP project synced: {result.project_name} (ID: {result.project_id})")


@cli.command()
@click.option("--url", required=True, help="Full URL to report artifacts to")
@click.option("--job-id", required=True, help="UUID of the completed job")
@click.option(
    "--error-message",
    default=None,
    help="Error message to report (sets status to error)",
)
@click.option(
    "--artifacts",
    multiple=True,
    required=False,
    help="Artifact as type:url (e.g., migration_plan:https://storage.example/migration-plan.md)",
)
@click.option(
    "--commit-id",
    default=None,
    help="Git commit SHA from the job's push to target repo",
)
@handle_exceptions
def report(url, job_id, error_message, artifacts, commit_id) -> None:
    """Report execution artifacts to the x2a API"""
    report_artifacts(
        url=url,
        job_id=job_id,
        artifacts=list(artifacts),
        error_message=error_message,
        commit_id=commit_id,
    )
    click.echo("Report sent successfully.")


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    cli()
