"""Publisher for Ansible roles to GitHub using GitOps approach."""

import subprocess
import traceback
from dataclasses import dataclass
from pathlib import Path

import requests
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.model import get_runnable_config
from src.publishers.tools import (
    _get_repo_path,
    copy_role_directory,
    create_directory_structure,
    generate_github_actions_workflow,
    generate_job_template_yaml,
    generate_playbook_yaml,
    github_commit_changes,
    github_create_pr,
    github_push_branch,
    verify_files_exist,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PublishState:
    """State for the publish workflow."""

    user_message: str
    path: str
    role: str
    role_path: str
    github_repository_url: str
    github_branch: str
    role_registered: bool = False
    job_template_name: str = ""
    job_template_created: bool = False
    publish_output: str = ""
    failed: bool = False
    failure_reason: str = ""
    # Workflow tracking
    directory_structure_created: bool = False
    role_copied: bool = False
    playbook_generated: bool = False
    job_template_generated: bool = False
    workflow_generated: bool = False
    files_verified: bool = False
    changes_committed: bool = False
    branch_pushed: bool = False
    pr_created: bool = False
    pr_url: str = ""
    skip_git: bool = False
    repo_path: str = ""
    pr_base_branch: str = "main"
    pr_head_branch: str = ""
    publish_dir: str = ""


class PublishWorkflow:
    """Implements a publishing workflow for Ansible roles using deterministic
    processes and LangGraph.

    Steps:
    1. Create directory structure
    2. Copy role directory
    3. Generate playbook
    4. Generate job template
    5. Generate GitHub Actions workflow
    6. Verify files exist
    7. Commit changes
    8. Push branch
    9. Create PR
    """

    # Node names for conditional edges
    NODE_COMMIT_CHANGES = "commit_changes"
    NODE_MARK_FAILED = "mark_failed"

    def __init__(self) -> None:
        """Initialize the publish workflow."""
        self._graph = self._build_workflow()
        logger.debug(
            f"Publish workflow graph: {self._graph.get_graph().draw_mermaid()}"
        )

    def _build_workflow(self) -> CompiledStateGraph:
        """Build the LangGraph workflow for publishing."""
        workflow = StateGraph(PublishState)
        workflow.add_node("create_structure", self._create_structure_node)
        workflow.add_node("copy_role", self._copy_role_node)
        workflow.add_node("generate_playbook", self._generate_playbook_node)
        workflow.add_node("generate_job_template", self._generate_job_template_node)
        workflow.add_node("generate_workflow", self._generate_workflow_node)
        workflow.add_node("verify_files", self._verify_files_node)
        workflow.add_node("commit_changes", self._commit_changes_node)
        workflow.add_node("push_branch", self._push_branch_node)
        workflow.add_node("create_pr", self._create_pr_node)
        workflow.add_node("mark_failed", self._mark_failed_node)

        workflow.add_edge(START, "create_structure")
        workflow.add_edge("create_structure", "copy_role")
        workflow.add_edge("copy_role", "generate_playbook")
        workflow.add_edge("generate_playbook", "generate_job_template")
        workflow.add_edge("generate_job_template", "generate_workflow")
        workflow.add_edge("generate_workflow", "verify_files")
        workflow.add_conditional_edges("verify_files", self._check_verification)
        workflow.add_edge("commit_changes", "push_branch")
        workflow.add_edge("push_branch", "create_pr")
        workflow.add_conditional_edges("create_pr", self._check_git_complete)
        workflow.add_edge("mark_failed", END)

        return workflow.compile()

    def _create_structure_node(self, state: PublishState) -> PublishState:
        """Node: Create directory structure for PR."""
        slog = logger.bind(phase="create_structure")
        slog.info("Creating directory structure")

        base_path = state.publish_dir
        structure = [
            "roles",
            "playbooks",
            "aap-config/job-templates",
            ".github/aap-workflow",
        ]

        try:
            create_directory_structure(base_path=base_path, structure=structure)
            state.directory_structure_created = True
            slog.info("Directory structure created successfully")
        except OSError as e:
            state.failed = True
            state.failure_reason = str(e)
            state.publish_output = str(e)
        return state

    def _copy_role_node(self, state: PublishState) -> PublishState:
        """Node: Copy role directory to publish directory."""
        slog = logger.bind(phase="copy_role")
        slog.info(f"Copying role from {state.role_path}")

        source_role_path = state.role_path
        destination_path = f"{state.publish_dir}/roles/{state.role}"

        try:
            copy_role_directory(
                source_role_path=source_role_path,
                destination_path=destination_path,
            )
            state.role_copied = True
            slog.info("Role copied successfully")
        except (ValueError, FileNotFoundError, OSError, RuntimeError) as e:
            state.failed = True
            state.failure_reason = str(e)
            state.publish_output = str(e)
        return state

    def _generate_playbook_node(self, state: PublishState) -> PublishState:
        """Node: Generate playbook YAML."""
        slog = logger.bind(phase="generate_playbook")
        slog.info("Generating playbook YAML")

        file_path = f"{state.publish_dir}/playbooks/{state.role}_deploy.yml"
        name = f"Deploy {state.role}"
        role_name = state.role

        try:
            generate_playbook_yaml(
                file_path=file_path,
                name=name,
                role_name=role_name,
            )
            state.playbook_generated = True
            slog.info("Playbook generated successfully")
        except (ValueError, OSError) as e:
            state.failed = True
            state.failure_reason = str(e)
            state.publish_output = str(e)
        return state

    def _generate_job_template_node(self, state: PublishState) -> PublishState:
        """Node: Generate job template YAML."""
        slog = logger.bind(phase="generate_job_template")
        slog.info("Generating job template YAML")

        file_path = (
            f"{state.publish_dir}/aap-config/job-templates/"
            f"{state.job_template_name}.yaml"
        )
        name = state.job_template_name
        playbook_path = f"playbooks/{state.role}_deploy.yml"
        inventory = "Default"
        role_name = state.role
        description = f"Deploy {state.role} role"

        try:
            generate_job_template_yaml(
                file_path=file_path,
                name=name,
                playbook_path=playbook_path,
                inventory=inventory,
                role_name=role_name,
                description=description,
            )
            state.job_template_generated = True
            state.job_template_created = True
            slog.info("Job template generated successfully")
        except (ValueError, OSError) as e:
            state.failed = True
            state.failure_reason = str(e)
            state.publish_output = str(e)
        return state

    def _generate_workflow_node(self, state: PublishState) -> PublishState:
        """Node: Generate GitHub Actions workflow."""
        slog = logger.bind(phase="generate_workflow")
        slog.info("Generating GitHub Actions workflow")

        file_path = (
            f"{state.publish_dir}/.github/aap-workflow/ansible-collection-import.yml"
        )

        try:
            generate_github_actions_workflow(file_path=file_path)
            state.workflow_generated = True
            slog.info("GitHub Actions workflow generated successfully")
        except OSError as e:
            state.failed = True
            state.failure_reason = str(e)
            state.publish_output = str(e)
        return state

    def _get_required_files(self, state: PublishState) -> list[str]:
        """Get list of required files to verify.

        This method can be overridden to customize which files are required.

        Args:
            state: Current publish state

        Returns:
            List of file paths to verify
        """
        return [
            f"{state.publish_dir}/roles/{state.role}",
            f"{state.publish_dir}/playbooks/{state.role}_deploy.yml",
            (
                f"{state.publish_dir}/aap-config/job-templates/"
                f"{state.job_template_name}.yaml"
            ),
            f"{state.publish_dir}/.github/aap-workflow/ansible-collection-import.yml",
        ]

    def _verify_files_node(self, state: PublishState) -> PublishState:
        """Node: Verify all required files exist."""
        slog = logger.bind(phase="verify_files")
        slog.info("Verifying files exist")

        required_files = self._get_required_files(state)

        try:
            verify_files_exist(file_paths=required_files)
            state.files_verified = True
            slog.info("All files verified successfully")
        except FileNotFoundError as e:
            state.failed = True
            state.failure_reason = str(e)
            state.publish_output = str(e)
        return state

    def _commit_changes_node(self, state: PublishState) -> PublishState:
        """Node: Commit changes to git."""
        slog = logger.bind(phase="commit_changes")
        slog.info("Committing changes to git")

        repository_url = state.github_repository_url
        directory = state.publish_dir
        commit_message = f"Add {state.role} role and related configurations"

        # Determine branch to use for commit/PR
        # If github_branch is the same as base branch, create a feature branch
        base_branch = state.pr_base_branch
        if state.github_branch == base_branch:
            # Create feature branch name
            feature_branch = f"publish/{state.role}"
            state.pr_head_branch = feature_branch
            slog.info(
                f"Branch '{base_branch}' is same as base. "
                f"Using feature branch: {feature_branch}"
            )
        else:
            state.pr_head_branch = state.github_branch

        branch = state.pr_head_branch

        # Calculate repo path before committing (needed for push later)
        repo_path = _get_repo_path(repository_url)
        state.repo_path = str(repo_path)

        try:
            commit_hash = github_commit_changes(
                repository_url=repository_url,
                directory=directory,
                commit_message=commit_message,
                branch=branch,
            )
            state.changes_committed = True
            slog.info(f"Changes committed successfully. Commit: {commit_hash}")
        except ValueError as e:
            # Validation errors are user input issues - provide clear feedback
            state.failed = True
            state.failure_reason = f"Validation failed: {e}"
            state.publish_output = (
                f"Invalid configuration: {e}. "
                "Please check your repository URL, branch, and directory."
            )
        except FileNotFoundError as e:
            state.failed = True
            state.failure_reason = f"Directory not found: {e}"
            state.publish_output = str(e)
        except subprocess.CalledProcessError as e:
            # Git errors might be retryable or need different handling
            state.failed = True
            state.failure_reason = f"Git operation failed: {e}"
            state.publish_output = (
                f"Git operation failed: {e}. "
                "This might be a temporary issue - you can try again."
            )
        except RuntimeError as e:
            state.failed = True
            state.failure_reason = str(e)
            state.publish_output = str(e)
        return state

    def _push_branch_node(self, state: PublishState) -> PublishState:
        """Node: Push branch to remote."""
        slog = logger.bind(phase="push_branch")
        slog.info("Pushing branch to remote")

        repository_url = state.github_repository_url
        branch = state.pr_head_branch
        repo_path = Path(state.repo_path) if state.repo_path else None

        try:
            github_push_branch(
                repository_url=repository_url,
                branch=branch,
                repo_path=repo_path,
                remote="origin",
                force=False,
            )
            state.branch_pushed = True
            slog.info("Branch pushed successfully")
        except ValueError as e:
            # Missing repo_path or branch - configuration issue
            state.failed = True
            state.failure_reason = f"Configuration error: {e}"
            state.publish_output = (
                f"Configuration error: {e}. "
                "This should not happen if previous steps succeeded."
            )
        except FileNotFoundError as e:
            state.failed = True
            state.failure_reason = f"Repository not found: {e}"
            state.publish_output = str(e)
        except subprocess.CalledProcessError as e:
            # Git push failures - might be auth, network, or conflict issues
            state.failed = True
            state.failure_reason = f"Failed to push branch: {e}"
            state.publish_output = (
                f"Failed to push branch: {e}. "
                "Check your authentication and network connection."
            )
        except RuntimeError as e:
            state.failed = True
            state.failure_reason = str(e)
            state.publish_output = str(e)
        return state

    def _create_pr_node(self, state: PublishState) -> PublishState:
        """Node: Create Pull Request."""
        slog = logger.bind(phase="create_pr")
        slog.info("Creating Pull Request")

        repository_url = state.github_repository_url
        title = f"Add {state.role} role and GitOps configuration"
        body = (
            f"This PR adds the {state.role} Ansible role and related "
            f"configurations for GitOps deployment to "
            f"Ansible Automation Platform.\n\n"
            f"- Role: {state.role}\n"
            f"- Playbook: {state.role}_deploy.yml\n"
            f"- Job Template: {state.job_template_name}\n"
            f"- GitHub Actions workflow for collection import"
        )
        head = state.pr_head_branch
        base = state.pr_base_branch

        try:
            pr_url = github_create_pr(
                repository_url=repository_url,
                title=title,
                body=body,
                head=head,
                base=base,
            )
            state.pr_url = pr_url
            state.pr_created = True
            state.publish_output = pr_url
            slog.info(f"Pull Request created successfully. URL: {pr_url}")
        except ValueError as e:
            # Missing token, invalid branches, etc.
            state.failed = True
            state.failure_reason = f"PR validation failed: {e}"
            state.publish_output = (
                f"Cannot create PR: {e}. "
                "Check your GITHUB_TOKEN and branch configuration."
            )
        except requests.exceptions.HTTPError as e:
            # API errors - rate limits, permissions, etc.
            state.failed = True
            state.failure_reason = f"GitHub API error: {e}"
            state.publish_output = (
                f"GitHub API error: {e}. "
                "This might be a rate limit or permission issue."
            )
        except requests.exceptions.RequestException as e:
            state.failed = True
            state.failure_reason = f"GitHub API request failed: {e}"
            state.publish_output = str(e)
        except RuntimeError as e:
            state.failed = True
            state.failure_reason = str(e)
            state.publish_output = str(e)
        return state

    def _check_verification(self, state: PublishState) -> str:
        """Conditional edge: Check if verification passed.

        Returns:
            Node name to transition to, or END to terminate workflow.
        """
        if state.failed:
            return self.NODE_MARK_FAILED
        if state.skip_git:
            return END
        return self.NODE_COMMIT_CHANGES

    def _check_git_complete(self, state: PublishState) -> str:
        """Conditional edge: Check if git steps completed successfully.

        Returns:
            Node name to transition to, or END to terminate workflow.
        """
        if state.failed:
            return self.NODE_MARK_FAILED
        return END

    def _mark_failed_node(self, state: PublishState) -> PublishState:
        """Node: Mark workflow as failed."""
        slog = logger.bind(phase="mark_failed")
        failure_reason = state.failure_reason or "Unknown error"
        slog.error(f"Workflow failed: {failure_reason}")
        return state

    def invoke(self, initial_state: PublishState) -> PublishState:
        """Execute publish workflow.

        Args:
            initial_state: PublishState with role information

        Returns:
            Updated PublishState with results
        """
        slog = logger.bind(phase="publish_role")
        slog.info("Starting publish workflow")

        try:
            result = self._graph.invoke(initial_state, config=get_runnable_config())
            final_state = PublishState(**result)

            if final_state.failed:
                slog.error(
                    f"Publish failed for role {final_state.role}: "
                    f"{final_state.failure_reason or 'Unknown error'}"
                )
                return final_state

            if final_state.skip_git:
                slog.info(
                    f"Publish completed successfully for role "
                    f"{final_state.role}! "
                    f"(Git steps skipped - files in "
                    f"{final_state.publish_dir}/)"
                )
                return final_state

            slog.info(f"Publish completed successfully for role {final_state.role}!")
            if final_state.pr_url:
                slog.info(f"PR URL: {final_state.pr_url}")

            return final_state

        except Exception as e:
            error_str = str(e)
            slog.error(f"Error in PublishWorkflow: {error_str}")
            slog.debug(f"Full traceback: {traceback.format_exc()}")

            initial_state.failed = True
            initial_state.failure_reason = f"Publish workflow error: {error_str}"
            initial_state.publish_output = (
                f"Unexpected error occurred. Error details: {error_str}"
            )
            return initial_state


def publish_role(
    role_name: str,
    role_path: str,
    github_repository_url: str,
    github_branch: str,
    skip_git: bool = False,
) -> PublishState:
    """Publish the role to Ansible Automation Platform.

    Args:
        role_name: Name of the role to publish
        role_path: Path to the role directory
        github_repository_url: GitHub repository URL
        github_branch: Branch name to use for the PR
        skip_git: If True, skip git steps (commit, push, PR).
                  Files will be created in a role-specific directory.

    Returns:
        PublishState with results
    """
    logger.info(f"Publishing: {role_name}")

    # Run the publish workflow
    publish_workflow = PublishWorkflow()
    initial_state = PublishState(
        user_message="",
        path="/",
        role=role_name,
        role_path=role_path,
        github_repository_url=github_repository_url,
        github_branch=github_branch,
        job_template_name=f"{role_name}_deploy",
        skip_git=skip_git,
        publish_dir=f"publish_results_{role_name}",
    )
    result = publish_workflow.invoke(initial_state)

    if result.failed:
        failure_reason = result.failure_reason or "Unknown error"
        logger.error(f"Publish failed for role {role_name}: {failure_reason}")
        return result

    logger.info(f"Publish completed successfully for role {role_name}!")
    return result
