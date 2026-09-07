"""Init workflow package for migration planning.

This package provides the init_project function that orchestrates
the migration planning workflow using InitAgent and StateGraph.
"""

from pathlib import Path

from src.const import METADATA_FILENAME
from src.init.init_agent import InitAgent
from src.init.init_state import InitState
from src.types import Telemetry
from src.utils.logging import get_logger

logger = get_logger(__name__)


# ~12k tokens at ~4 chars/token
DIR_LISTING_CHAR_LIMIT = 50_000


def list_directory_tree(dir_path: str) -> str:
    """Recursively list full directory structure as an indented tree, excluding hidden paths.

    Truncates at DIR_LISTING_CHAR_LIMIT chars and appends a note so the model
    knows to use list_directory for paths not shown.
    """
    path = Path(dir_path)
    entries = []
    for item in path.rglob("*"):
        relative = item.relative_to(path)
        if any(part.startswith(".") for part in relative.parts):
            continue
        entries.append(relative.parts)
    entries.sort()
    lines = []
    total = 0
    for parts in entries:
        indent = "  " * (len(parts) - 1)
        suffix = "/" if (path / Path(*parts)).is_dir() else ""
        line = f"{indent}{parts[-1]}{suffix}"
        total += len(line) + 1
        if total > DIR_LISTING_CHAR_LIMIT:
            lines.append("[tree truncated — use list_directory for remaining paths]")
            break
        lines.append(line)
    return "\n".join(lines)


def init_project(user_requirements: str, source_dir: str = ".", refresh: bool = False):
    """Initialize project with migration planning and metadata generation.

    Uses InitAgent with StateGraph workflow following the exporter pattern.

    Args:
        user_requirements: User's migration requirements and context
        source_dir: Source directory to analyze (default: current directory)
        refresh: If True and migration-plan.md exists, skip plan generation
                 and only regenerate metadata (default: False)

    Returns:
        Final InitState with migration plan and metadata

    Raises:
        RuntimeError: If the init workflow fails
    """
    slog = logger.bind(phase="init_project", refresh=refresh)
    slog.info("Starting init workflow...")
    slog.debug(f"User requirements: {user_requirements}")
    slog.debug(f"Source dir: {source_dir}")
    slog.debug(f"Refresh mode: {refresh}")

    files = list_directory_tree(source_dir)

    # Create initial state
    telemetry = Telemetry(phase="init")
    initial_state = InitState(
        user_message=user_requirements,
        path=source_dir,
        directory_listing=files,
        refresh=refresh,
        telemetry=telemetry,
    )

    # Create and invoke agent
    agent = InitAgent()
    result_state = agent(initial_state)

    # Stop telemetry and capture summary
    telemetry.stop()

    if result_state.failed:
        summary_text = f"Init failed: {result_state.failure_reason}"
    else:
        summary_text = "\n".join(
            [
                "Init workflow completed successfully",
                f"Migration plan: {result_state.migration_plan_path}",
                f"Metadata file: {METADATA_FILENAME} ({len(result_state.metadata_items)} modules)",
            ]
        )

    telemetry.with_summary(summary_text).save()
    slog.info(f"Telemetry summary:\n{telemetry.to_summary()}")

    # Handle results
    if result_state.failed:
        slog.error(f"Init failed: {result_state.failure_reason}")
        raise RuntimeError(result_state.failure_reason)

    slog.info("Init workflow completed successfully")
    slog.info(f"Migration plan: {result_state.migration_plan_path}")
    slog.info(
        f"Metadata file: {METADATA_FILENAME} ({len(result_state.metadata_items)} modules)"
    )

    return result_state


__all__ = ["init_project", "list_directory_tree"]
