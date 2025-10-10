import click
import logging
import os

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_community.tools.file_management.write import WriteFileTool
from langgraph.prebuilt import create_react_agent
from pathlib import Path

from prompts.get_prompt import get_prompt
from src.model import get_model
from src.const import MIGRATION_PLAN_FILE

logger = logging.getLogger(__name__)


def create_migration_agent():
    """Create a LangGraph agent with file management tools for migration planning"""
    logger.info("Creating migration agent")

    model = get_model()

    # Set up file management tools
    tools = [
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

    # Create the agent with higher recursion limit
    agent = create_react_agent(
        model=model,
        tools=tools,
        prompt=system_prompt,
    )
    return agent


def list_with_depth(dir_path, max_depth=2):
    path = Path(dir_path)
    items = []
    for item in path.rglob("*"):
        relative = item.relative_to(path)
        if any(part.startswith(".") for part in relative.parts):
            continue
        depth = len(relative.parts)
        if depth <= max_depth:
            items.append(str(relative))
    return "\n".join(sorted(items))


def init_project(user_requirements, source_dir="."):
    """Initialize project with migration planning"""
    logger.info("Analyzing repository for migration planning...")
    logger.debug(f"User requirements: {user_requirements}")

    # Change to source directory if specified
    os.chdir(source_dir)

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
            config={
                "recursion_limit": 50,
                "max_concurrency": 50,
            },
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
        if os.path.exists(MIGRATION_PLAN_FILE):
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
        click.echo(f"❌ Error during migration planning: {str(e)}")
        raise
