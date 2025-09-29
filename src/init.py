import click
import logging
import os

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_community.tools.file_management.write import WriteFileTool
from langgraph.prebuilt import create_react_agent
from prompts.get_prompt import get_prompt
from src.model import get_model


def create_migration_agent():
    """Create a LangGraph agent with file management tools for migration planning"""

    model = get_model()

    # Set up file management tools
    tools = [
        FileSearchTool(),
        ListDirectoryTool(),
        ReadFileTool(),
        WriteFileTool(),
    ]

    # Get the migration planning system prompt
    system_prompt = get_prompt("migration")

    # Create the agent with higher recursion limit
    agent = create_react_agent(
        model=model,
        tools=tools,
        prompt=system_prompt,
    )
    return agent


def init_project(message, target_dir="."):
    """Initialize project with migration planning"""
    click.echo("Analyzing repository for migration planning...")
    click.echo(f"User requirements: {message}")

    # Change to target repository directory if specified
    os.chdir(target_dir)

    try:
        # Create the migration planning agent
        agent = create_migration_agent()

        # Prepare the user message for migration analysis
        user_message = f"""
        Please analyze this repository for migration to Ansible. 

        User requirements: {message}

        Start by exploring the repository structure to understand what technology stack is currently being used, then create a comprehensive migration-plan.md file that follows the template structure. Focus on:

        1. Identifying the current technology (Chef, Puppet, Salt, etc.)
        2. Cataloging all modules/cookbooks/manifests
        3. Mapping dependencies and external requirements
        4. Identifying security configurations
        5. Estimating migration complexity and timeline
        6. Providing coordination guidance for teams

        Write the complete migration plan to a file called 'migration-plan.md' in the repository root.
        """

        # Execute the agent with higher recursion limit
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_message}]}, 
            config={
                "recursion_limit": 50,
                "max_concurrency": 50,
            }
        )

        # Debug: Print result structure and last AI message
        click.echo("\n🔍 Debug Info:")
        click.echo(f"Result type: {type(result)}")
        click.echo(f"Result keys: {list(result.keys()) if hasattr(result, 'keys') else 'N/A'}")

        # Print last AI message and ALL tool calls made during conversation
        for message in result["messages"]:
            message.pretty_print()
        # Check if the migration plan was actually created
        if os.path.exists("migration-plan.md"):
            click.echo("✅ Migration plan generated successfully!")
            click.echo("📄 Check 'migration-plan.md' for the detailed migration analysis.")
        else:
            click.echo("⚠️  Agent completed but migration-plan.md was not created.")
        return result

    except Exception as e:
        click.echo(f"❌ Error during migration planning: {str(e)}")
        raise
