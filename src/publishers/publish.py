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
    github_create_repository,
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
    github_owner: str
    github_branch: str
    github_repository_url: str = ""  # Set after repository creation
    role_registered: bool = False
    job_template_name: str = ""
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
    repository_created: bool = False
    skip_git: bool = False
    repo_path: str = ""
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
    7. Create GitHub repository (if not skip_git)
    8. Commit changes (if not skip_git)
    9. Push branch (if not skip_git)
    10. Display summary
    """

    # Node names for conditional edges
    NODE_CREATE_REPOSITORY = "create_repository"
    NODE_SUMMARY = "summary"
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
        workflow.add_node("create_repository", self._create_repository_node)
        workflow.add_node("commit_changes", self._commit_changes_node)
        workflow.add_node("push_branch", self._push_branch_node)
        workflow.add_node("summary", self._summary_node)
        workflow.add_node("mark_failed", self._mark_failed_node)

        workflow.add_edge(START, "create_structure")
        workflow.add_edge("create_structure", "copy_role")
        workflow.add_edge("copy_role", "generate_playbook")
        workflow.add_edge("generate_playbook", "generate_job_template")
        workflow.add_edge("generate_job_template", "generate_workflow")
        workflow.add_edge("generate_workflow", "verify_files")
        workflow.add_conditional_edges("verify_files", self._check_verification)
        workflow.add_edge("create_repository", "commit_changes")
        workflow.add_conditional_edges("commit_changes", self._check_commit_result)
        workflow.add_edge("push_branch", "summary")
        workflow.add_edge("summary", END)
        workflow.add_edge("mark_failed", "summary")

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
            ".github/workflows",
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
            f"{state.publish_dir}/aap-config/job-templates/{state.role}_deploy.yaml"
        )
        name = f"{state.role}_deploy"
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

        file_path = f"{state.publish_dir}/.github/workflows/deploy.yml"

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
            (f"{state.publish_dir}/aap-config/job-templates/{state.role}_deploy.yaml"),
            f"{state.publish_dir}/.github/workflows/deploy.yml",
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

    def _create_repository_node(self, state: PublishState) -> PublishState:
        """Node: Create GitHub repository."""
        slog = logger.bind(phase="create_repository")
        slog.info("Creating GitHub repository")

        owner = state.github_owner
        repo_name = f"{state.role}-gitops"
        description = f"GitOps repository for {state.role} Ansible role deployment"

        try:
            repository_url = github_create_repository(
                owner=owner,
                repo_name=repo_name,
                description=description,
                private=False,
            )
            state.github_repository_url = repository_url
            state.repository_created = True
            slog.info(f"Repository created successfully: {repository_url}")
        except ValueError as e:
            state.failed = True
            state.failure_reason = f"Repository creation validation failed: {e}"
            state.publish_output = (
                f"Cannot create repository: {e}. "
                "Check your GITHUB_TOKEN and owner configuration."
            )
        except requests.exceptions.HTTPError as e:
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

    def _commit_changes_node(self, state: PublishState) -> PublishState:
        """Node: Commit changes to git."""
        slog = logger.bind(phase="commit_changes")
        slog.info("Committing changes to git")

        repository_url = state.github_repository_url
        # Resolve to absolute path to ensure it's found regardless of cwd
        directory = str(Path(state.publish_dir).resolve())
        slog.info(f"Committing deployment directory: {directory}")
        commit_message = f"Add {state.role} role and related configurations"

        # For new repository, push directly to the specified branch (usually main)
        branch = state.github_branch

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
            # All RuntimeErrors are failures
            state.failed = True
            state.failure_reason = str(e)
            state.publish_output = str(e)
        return state

    def _push_branch_node(self, state: PublishState) -> PublishState:
        """Node: Push branch to remote."""
        slog = logger.bind(phase="push_branch")
        slog.info("Pushing branch to remote")

        repository_url = state.github_repository_url
        branch = state.github_branch
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

    def _check_verification(self, state: PublishState) -> str:
        """Conditional edge: Check if verification passed.

        Returns:
            Node name to transition to, or END to terminate workflow.
        """
        if state.failed:
            return self.NODE_MARK_FAILED
        if state.skip_git:
            return self.NODE_SUMMARY
        return self.NODE_CREATE_REPOSITORY

    def _check_commit_result(self, state: PublishState) -> str:
        """Conditional edge: Check if commit completed successfully.

        Returns:
            Node name to transition to.
        """
        if state.failed:
            return self.NODE_SUMMARY  # Go to summary to show what happened
        return "push_branch"

    def _summary_node(self, state: PublishState) -> PublishState:
        """Node: Display summary of what was done."""
        slog = logger.bind(phase="summary")

        summary_lines = []
        summary_lines.append("\n" + "=" * 80)
        if state.failed:
            summary_lines.append("PUBLISH FAILED")
        else:
            summary_lines.append("PUBLISH SUMMARY")
        summary_lines.append("=" * 80)

        # Show failure information if failed
        if state.failed:
            summary_lines.append("\nError:")
            summary_lines.append(f"  {state.failure_reason or 'Unknown error'}")
            summary_lines.append("\nWhat Happened:")
            if "already exists in repository" in (state.failure_reason or ""):
                summary_lines.append(
                    f"  The branch '{state.github_branch}' already exists "
                    f"in the repository."
                )
                summary_lines.append(
                    "  Cannot create a duplicate branch. "
                    "Please use a different branch name."
                )
            else:
                summary_lines.append("  An error occurred during the publish process.")
                summary_lines.append("  Check the error message above for details.")

        # Files created - always show
        summary_lines.append("\nFiles Created:")
        summary_lines.append(f"  - Role: {state.publish_dir}/roles/{state.role}/")
        summary_lines.append(
            f"  - Playbook: {state.publish_dir}/playbooks/{state.role}_deploy.yml"
        )
        summary_lines.append(
            f"  - Job Template: "
            f"{state.publish_dir}/aap-config/job-templates/"
            f"{state.role}_deploy.yaml"
        )
        if state.workflow_generated:
            summary_lines.append(
                f"  - GitHub Actions: {state.publish_dir}/.github/workflows/deploy.yml"
            )

        # Credentials needed - only show if not pushed yet and not failed
        if not state.repository_created and not state.failed:
            summary_lines.append("\nGitHub Credentials Required:")
            summary_lines.append(
                "  To push to GitHub, you need to set up authentication:"
            )
            summary_lines.append(
                "  1. Create a Personal Access Token (PAT) with 'repo' scope:"
            )
            summary_lines.append("     - Go to: https://github.com/settings/tokens")
            summary_lines.append("     - Click 'Generate new token (classic)'")
            summary_lines.append("     - Select 'repo' scope")
            summary_lines.append("     - Copy the token")
            summary_lines.append("  2. Set the token as an environment variable:")
            summary_lines.append("     export GITHUB_TOKEN='your_token_here'")

        # Where it will be executed
        summary_lines.append("\nExecution Location:")
        if state.repository_created and state.branch_pushed:
            summary_lines.append(f"  Repository: {state.github_repository_url}")
            summary_lines.append(f"  Branch: {state.github_branch}")
            summary_lines.append("  The deployment has been pushed to the repository.")
            summary_lines.append(
                "\nPlease configure the AAP secrets in the repository "
                "to activate the deployment actions:"
            )
            summary_lines.append("  - AAP_CONTROLLER_URL")
            summary_lines.append("  - AAP_USERNAME")
            summary_lines.append("  - AAP_PASSWORD")
        else:
            summary_lines.append(f"  Local directory: {state.publish_dir}")
            if not state.skip_git and not state.failed:
                summary_lines.append("  To push to GitHub:")
                summary_lines.append("    1. Set GITHUB_TOKEN environment variable")
                summary_lines.append(f"    2. Run: cd {state.publish_dir}")
                summary_lines.append("    3. Initialize git: git init")
                summary_lines.append(
                    "    4. Add remote: git remote add origin <repository-url>"
                )
                push_cmd = (
                    f"    5. Commit and push: git add . && "
                    f"git commit -m 'Initial commit' && "
                    f"git push -u origin {state.github_branch}"
                )
                summary_lines.append(push_cmd)

        summary_lines.append("\n" + "=" * 80)

        summary_text = "\n".join(summary_lines)
        state.publish_output = summary_text
        print(summary_text)
        slog.info("Summary displayed")

        return state

    def _mark_failed_node(self, state: PublishState) -> PublishState:
        """Node: Mark workflow as failed and proceed to summary."""
        slog = logger.bind(phase="mark_failed")
        failure_reason = state.failure_reason or "Unknown error"
        slog.error(f"Workflow failed: {failure_reason}")
        # Summary node will display the failure details
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

            # Summary is already displayed by the summary node
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
    github_owner: str,
    github_branch: str,
    base_path: str | None = None,
    skip_git: bool = False,
) -> PublishState:
    """Publish the role to Ansible Automation Platform.

    Args:
        role_name: Name of the role to publish
        role_path: Path to the role directory
            (e.g., <path>/ansible/roles/{role})
        github_owner: GitHub user or organization name
        github_branch: Branch name to push to (default: main)
        base_path: Base path for constructing deployment path
            (defaults to parent of role_path's parent)
        skip_git: If True, skip git steps (create repo, commit, push).
                  Files will be created in a role-specific directory.

    Returns:
        PublishState with results
    """
    logger.info(f"Publishing: {role_name}")

    # Determine base path and construct deployment path
    role_path_obj = Path(role_path)
    if base_path:
        base_path_obj = Path(base_path)
        deployment_path = base_path_obj / "ansible" / "deployments" / role_name
    else:
        # Extract ansible path from role_path:
        # <path>/ansible/roles/{role} -> <path>/ansible
        # Go up two levels from role_path to get ansible directory
        # (role -> roles -> ansible)
        ansible_path = role_path_obj.parent.parent
        # Construct deployment path at same level as roles/
        deployment_path = ansible_path / "deployments" / role_name
        base_path_obj = ansible_path.parent

    # Run the publish workflow
    publish_workflow = PublishWorkflow()
    initial_state = PublishState(
        user_message="",
        path=str(base_path_obj),
        role=role_name,
        role_path=role_path,
        github_owner=github_owner,
        github_branch=github_branch,
        job_template_name=f"{role_name}_deploy",
        skip_git=skip_git,
        publish_dir=str(deployment_path),
    )
    result = publish_workflow.invoke(initial_state)

    if result.failed:
        failure_reason = result.failure_reason or "Unknown error"
        logger.error(f"Publish failed for role {role_name}: {failure_reason}")
        return result

    logger.info(f"Publish completed successfully for role {role_name}!")
    return result
