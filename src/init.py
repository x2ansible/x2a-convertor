from collections.abc import Sequence
from pathlib import Path

import click
from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_community.tools.file_management.write import WriteFileTool
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from prompts.get_prompt import get_prompt
from src.const import MIGRATION_PLAN_FILE
from src.model import get_model, get_runnable_config
from src.utils.logging import get_logger

logger = get_logger(__name__)


def create_migration_agent() -> CompiledStateGraph:
    """Create a LangGraph agent with file management tools for migration planning"""
    logger.info("Creating migration agent")

    model = get_model()

    # Set up file management tools
    tools: Sequence[BaseTool] = [
        FileSearchTool(),
        ListDirectoryTool(),
        ReadFileTool(),
        WriteFileTool(),
    ]

    # Get the migration planning system prompt
    system_prompt = get_prompt("init_migration_instructions").format(
        migration_plan_file=MIGRATION_PLAN_FILE
    )
    logger.debug(f"System prompt: {system_prompt}")

    # pyrefly: ignore
    agent = create_react_agent(
        model=model,
        tools=tools,
        prompt=system_prompt,
    )
    return agent


def list_with_depth(dir_path: str, max_depth=2) -> str:
    path = Path(dir_path)
    items: list[str] = []
    for item in path.rglob("*"):
        relative = item.relative_to(path)
        if any(part.startswith(".") for part in relative.parts):
            continue
        depth = len(relative.parts)
        if depth <= max_depth:
            items.append(str(relative))
    return "\n".join(sorted(items))


def init_project(user_requirements, source_dir: str = "."):
    """Initialize project with migration planning"""
    logger.info("Analyzing repository for migration planning...")
    logger.debug(f"User requirements: {user_requirements}")

    try:
        # Create the migration planning agent
        agent = create_migration_agent()
        files = list_with_depth(".", max_depth=3)

        # Prepare the user message for migration analysis
        user_message = get_prompt("init_migration_plan_request").format(
            user_requirements=user_requirements,
            migration_plan_file=MIGRATION_PLAN_FILE,
            files=files,
        )
        logger.debug(f"Initial user prompt: {user_message}")
        # Execute the agent with higher recursion limit
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_message}]},
            config=get_runnable_config(),
        )

        logger.debug("Migration agent result:")
        logger.debug(f"Result type: {type(result)}")
        logger.debug(
            f"Result keys: {list(result.keys()) if hasattr(result, 'keys') else 'N/A'}"
        )

        # Print last AI message and ALL tool calls made during conversation
        for user_requirements in result["messages"]:
            user_requirements.pretty_print()

        # Check if the migration plan was actually created
        if Path(MIGRATION_PLAN_FILE).exists():
            click.echo("✅ Migration plan generated successfully!")
            click.echo(
                f"📄 Check '{MIGRATION_PLAN_FILE}' for the detailed migration analysis."
            )
        else:
            click.echo(
                f"⚠️  Agent completed but '{MIGRATION_PLAN_FILE}' was not created."
            )
        return result

    except Exception as e:
        click.echo(f"❌ Error during migration planning: {e!s}")
        raise
