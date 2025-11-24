from collections.abc import Callable
from typing import ClassVar, TypedDict

from langchain_community.tools.file_management.file_search import (
    FileSearchTool,
)
from langchain_community.tools.file_management.list_dir import (
    ListDirectoryTool,
)
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

from prompts.get_prompt import get_prompt
from src.model import get_model, get_runnable_config, report_tool_calls
from src.utils.logging import get_logger
from tools.copy_role_directory import CopyRoleDirectoryTool
from tools.create_directory_structure import CreateDirectoryStructureTool
from tools.generate_github_actions_workflow import (
    GenerateGitHubActionsWorkflowTool,
)
from tools.generate_job_template_yaml import GenerateJobTemplateYAMLTool
from tools.generate_playbook_yaml import GeneratePlaybookYAMLTool
from tools.github_commit_changes import GitHubCommitChangesTool
from tools.github_create_pr import GitHubCreatePRTool
from tools.github_push_branch import GitHubPushBranchTool

logger = get_logger(__name__)


class SourceMetadata(BaseModel):
    """Structured output for source metadata"""

    path: str


class PublishState(TypedDict):
    user_message: str
    path: str
    role: str
    role_path: str
    github_repository_url: str
    github_branch: str
    role_registered: bool
    job_template_name: str
    job_template_created: bool
    publish_output: str
    failed: bool
    failure_reason: str


class PublishAgent:
    """Agent for publishing Ansible roles to GitHub using GitOps approach.

    Uses a react agent pattern where the LLM decides which tools to use
    based on the task description. The agent:
    1. Finds the ansible code needed to upload
    2. Generates directory structure for PR
    3. Adds the ansible code to that directory in the specific tree
       (roles, templates etc)
    4. Generates a playbook that uses the role
    5. Generates a job template that references the playbook
    6. Generates GitHub Actions workflow for GitOps
    7. Verifies all generated files exist in the publish_results/ directory
    8. Commits changes to git
    9. Pushes branch to remote
    10. Creates a Pull Request for the publish_results/ directory to the
        GitHub repository
    """

    # Tools available to the agent
    # Matching successful run: 9 tools with ~2034 chars total
    # Using separate tools like the successful run (not consolidated)
    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: FileSearchTool(),
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
        lambda: CreateDirectoryStructureTool(),
        lambda: CopyRoleDirectoryTool(),
        lambda: GeneratePlaybookYAMLTool(),
        lambda: GenerateJobTemplateYAMLTool(),
        lambda: GenerateGitHubActionsWorkflowTool(),
        lambda: GitHubCommitChangesTool(),
        lambda: GitHubPushBranchTool(),
        lambda: GitHubCreatePRTool(),
    ]

    SYSTEM_PROMPT_NAME = "publish_role_system"

    def __init__(self, model=None) -> None:
        """Initialize publish agent with model.

        Args:
            model: LLM model to use (defaults to get_model())
        """
        self.model = model or get_model()

    def _create_react_agent(self, state: PublishState):
        """Create a react agent with publishing tools.

        Args:
            state: PublishState with role information

        Returns:
            Configured react agent
        """
        logger.info("Creating PublishAgent react agent")

        # Build tools from base tools
        tools = [factory() for factory in self.BASE_TOOLS]

        # Log tool info for debugging context size
        tool_desc_size = sum(
            len(str(tool.description) if hasattr(tool, "description") else "")
            for tool in tools
        )
        logger.debug(f"Number of tools: {len(tools)}")
        logger.debug(f"Total tool description size: ~{tool_desc_size} chars")

        return create_react_agent(model=self.model, tools=tools)  # pyrefly: ignore

    def invoke(self, initial_state: PublishState) -> PublishState:
        """Execute publish workflow using react agent.

        The agent will use tools autonomously to:
        1. Find the ansible code needed to upload
        2. Generate directory structure for PR
        3. Add the ansible code to that directory in the specific tree
           (roles, templates etc)
        4. Generate a playbook that uses the role
        5. Generate a job template that references the playbook
        6. Generate GitHub Actions workflow for GitOps
        7. Verify all generated files exist
        8. Commit changes to git
        9. Push branch to remote
        10. Create the PR via the tool

        Args:
            initial_state: PublishState with role information

        Returns:
            Updated PublishState with results
        """
        slog = logger.bind(phase="publish_role")
        slog.info("Publishing role using GitOps approach")

        role_name = initial_state["role"]
        role_path = initial_state["role_path"]
        github_repo = initial_state["github_repository_url"]
        github_branch = initial_state["github_branch"]
        job_template_name = initial_state["job_template_name"]

        # Build the task prompt - restored to match successful run
        system_prompt = get_prompt(self.SYSTEM_PROMPT_NAME)

        # Build tools to calculate size before creating agent
        tools = [factory() for factory in self.BASE_TOOLS]
        tool_desc_size = sum(
            len(str(tool.description) if hasattr(tool, "description") else "")
            for tool in tools
        )
        tool_names = [
            tool.name if hasattr(tool, "name") else "unknown" for tool in tools
        ]
        slog.debug(f"Tools before agent creation: {len(tools)} tools - {tool_names}")

        agent = self._create_react_agent(initial_state)
        # Make paths explicit and emphasize they MUST be created
        user_prompt = (
            f"Publish the Ansible role '{role_name}' to GitHub "
            f"using GitOps approach.\n\n"
            f"Role Information:\n"
            f"- Role name: {role_name}\n"
            f"- Role path: {role_path}\n"
            f"- GitHub repository: {github_repo}\n"
            f"- GitHub branch: {github_branch}\n"
            f"- Job template name: {job_template_name}\n\n"
            f"IMPORTANT: All files must be created in the 'publish_results/' "
            f"directory at the root level. This directory will contain the "
            f"entire PR structure.\n\n"
            f"Follow the workflow in the system prompt to:\n"
            f"1. Find the ansible code needed to upload\n"
            f"2. Generate directory structure for PR in publish_results/\n"
            f"3. Add the ansible code to publish_results/ in the specific "
            f"tree (roles, templates etc)\n"
            f"4. Generate a playbook that uses the role "
            f"(save to publish_results/playbooks/{role_name}_deploy.yml)\n"
            f"5. Generate a job template that references the playbook "
            f"(save to publish_results/aap-config/job-templates/"
            f"{job_template_name}.yaml)\n"
            f"6. Generate GitHub Actions workflow for GitOps "
            f"(save to publish_results/.github/workflows/"
            f"ansible-collection-import.yml)\n"
            f"7. Verify all generated files exist in publish_results/ "
            f"before proceeding\n"
            f"8. Commit changes using github_commit_changes tool\n"
            f"   - repository_url: {github_repo}\n"
            f"   - Use a feature branch name (e.g., 'publish-{role_name}')\n"
            f"   - Commit message should describe the role being published\n"
            f"9. Push branch using github_push_branch tool\n"
            f"   - repository_url: {github_repo}\n"
            f"   - Use the same branch name from step 8\n"
            f"10. Create a Pull Request using github_create_pr tool\n"
            f"   - Use the same branch name from steps 8-9\n"
            f"   - Include title and description about GitOps sync to AAP\n\n"
            f"Use the tools available to complete each step. "
            f"Report any errors clearly.\n\n"
            f"CRITICAL: You MUST complete ALL 10 steps. "
            f"Do NOT stop until you have successfully created the PR (step 10). "
            f"The task is NOT complete until you have a PR URL."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            slog.info(f"PublishAgent starting for role: {role_name}")
            # Calculate total message size (approximate)
            total_size = len(system_prompt) + len(user_prompt) + tool_desc_size
            slog.debug(
                f"System prompt: {len(system_prompt)} chars, "
                f"User prompt: {len(user_prompt)} chars, "
                f"Total message size: ~{total_size} chars"
            )
            slog.debug("Invoking react agent...")
            slog.debug(f"Messages being sent: {len(messages)} messages")
            slog.debug(f"First message type: {type(messages[0])}")
            config = get_runnable_config()
            slog.debug(f"Config: {config}")
            result = agent.invoke({"messages": messages}, config=config)

            slog.info(f"Publish agent tools: {report_tool_calls(result).to_string()}")

            # Extract the final message from the agent response
            final_message = result.get("messages", [])[-1]
            if hasattr(final_message, "content"):
                content = final_message.content
            else:
                content = str(final_message)

            # Update state with results
            initial_state["publish_output"] = content
            initial_state["failed"] = "ERROR" in content.upper()
            if initial_state["failed"]:
                initial_state["failure_reason"] = content
            else:
                # Mark steps as completed if no errors
                initial_state["job_template_created"] = True

            slog.info(f"PublishAgent completed for role: {role_name}")

        except Exception as e:
            error_str = str(e)
            slog.error(f"Error in PublishAgent: {error_str}")
            slog.error(
                f"Error type: {type(e).__name__}, Role: {role_name}, Path: {role_path}"
            )
            # Log full exception details for debugging
            import traceback

            slog.debug(f"Full traceback: {traceback.format_exc()}")
            exception_args = e.args if hasattr(e, "args") else "N/A"
            slog.debug(f"Exception args: {exception_args}")
            if hasattr(e, "__cause__") and e.__cause__:
                slog.debug(f"Exception cause: {e.__cause__}")
            if hasattr(e, "__context__") and e.__context__:
                slog.debug(f"Exception context: {e.__context__}")

            initial_state["failed"] = True
            # Extract main error message if it's a complex error
            main_error = error_str.split(" - ")[0] if " - " in error_str else error_str
            initial_state["failure_reason"] = f"Publish agent error: {main_error}"
            initial_state["publish_output"] = (
                f"ERROR: LLM API error occurred. "
                f"This may be a temporary issue with the model provider. "
                f"Error details: {error_str}"
            )

        return PublishState(**initial_state)


def publish_role(
    role_name: str,
    role_path: str,
    github_repository_url: str,
    github_branch: str,
) -> PublishState:
    """Publish the role to Ansible Automation Platform"""
    logger.info(f"Publishing: {role_name}")

    # Run the publish agent
    publish_agent = PublishAgent()
    initial_state = PublishState(
        user_message="",
        path="/",
        role=role_name,
        role_path=role_path,
        github_repository_url=github_repository_url,
        github_branch=github_branch,
        role_registered=False,
        job_template_name=f"{role_name}_deploy",
        job_template_created=False,
        publish_output="",
        failed=False,
        failure_reason="",
    )
    result = publish_agent.invoke(initial_state)

    if result["failed"]:
        failure_reason = result.get("failure_reason", "Unknown error")
        logger.error(f"Publish failed for role {role_name}: {failure_reason}")
    else:
        logger.info(f"Publish completed successfully for role {role_name}!")

    return PublishState(**result)
