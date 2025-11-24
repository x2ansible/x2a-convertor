"""Publisher for Ansible roles to GitHub using GitOps approach."""

import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langgraph.graph import END, START, StateGraph

from src.model import get_runnable_config
from src.publishers.tools import (
    _get_repo_path,
    create_directory_structure,
    copy_role_directory,
    generate_playbook_yaml,
    generate_job_template_yaml,
    generate_github_actions_workflow,
    verify_files_exist,
    github_commit_changes,
    github_push_branch,
    github_create_pr,
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
    def __init__(self) -> None:
        """Initialize the publish workflow."""
        self._graph = self._build_workflow()
        mermaid_graph = self._graph.get_graph().draw_mermaid()
        logger.debug("Publish workflow: " + mermaid_graph)

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow for publishing."""
        workflow = StateGraph(PublishState)
        workflow.add_node("create_structure", self._create_structure_node)
        workflow.add_node("copy_role", self._copy_role_node)
        workflow.add_node("generate_playbook", self._generate_playbook_node)
        workflow.add_node(
            "generate_job_template", self._generate_job_template_node
        )
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
        workflow.add_conditional_edges(
            "verify_files", self._check_verification
        )
        workflow.add_edge("commit_changes", "push_branch")
        workflow.add_edge("push_branch", "create_pr")
        workflow.add_conditional_edges("create_pr", self._check_git_complete)
        workflow.add_edge("mark_failed", END)

        return workflow.compile()

    def _create_structure_node(self, state: PublishState) -> PublishState:
        """Node: Create directory structure for PR."""
        slog = logger.bind(phase="create_structure")
        slog.info("Creating directory structure")

        base_path = "publish_results"
        structure = [
            "roles",
            "playbooks",
            "aap-config/job-templates",
            ".github/workflows",
        ]

        result = create_directory_structure(
            base_path=base_path, structure=structure
        )
        if result.startswith("ERROR"):
            state.failed = True
            state.failure_reason = result
            state.publish_output = result
            return state

        state.directory_structure_created = True
        slog.info("Directory structure created successfully")
        return state

    def _copy_role_node(self, state: PublishState) -> PublishState:
        """Node: Copy role directory to publish_results."""
        slog = logger.bind(phase="copy_role")
        slog.info(f"Copying role from {state.role_path}")

        source_role_path = state.role_path
        destination_path = (
            f"publish_results/roles/{state.role}"
        )

        result = copy_role_directory(
            source_role_path=source_role_path,
            destination_path=destination_path,
        )
        if result.startswith("ERROR"):
            state.failed = True
            state.failure_reason = result
            state.publish_output = result
            return state

        state.role_copied = True
        slog.info("Role copied successfully")
        return state

    def _generate_playbook_node(self, state: PublishState) -> PublishState:
        """Node: Generate playbook YAML."""
        slog = logger.bind(phase="generate_playbook")
        slog.info("Generating playbook YAML")

        file_path = (
            f"publish_results/playbooks/{state.role}_deploy.yml"
        )
        name = f"Deploy {state.role}"
        role_name = state.role

        result = generate_playbook_yaml(
            file_path=file_path,
            name=name,
            role_name=role_name,
        )
        if result.startswith("ERROR"):
            state.failed = True
            state.failure_reason = result
            state.publish_output = result
            return state

        state.playbook_generated = True
        slog.info("Playbook generated successfully")
        return state

    def _generate_job_template_node(self, state: PublishState) -> PublishState:
        """Node: Generate job template YAML."""
        slog = logger.bind(phase="generate_job_template")
        slog.info("Generating job template YAML")

        file_path = (
            f"publish_results/aap-config/job-templates/"
            f"{state.job_template_name}.yaml"
        )
        name = state.job_template_name
        playbook_path = f"playbooks/{state.role}_deploy.yml"
        inventory = "Default"
        role_name = state.role
        description = f"Deploy {state.role} role"

        result = generate_job_template_yaml(
            file_path=file_path,
            name=name,
            playbook_path=playbook_path,
            inventory=inventory,
            role_name=role_name,
            description=description,
        )
        if result.startswith("ERROR"):
            state.failed = True
            state.failure_reason = result
            state.publish_output = result
            return state

        state.job_template_generated = True
        state.job_template_created = True
        slog.info("Job template generated successfully")
        return state

    def _generate_workflow_node(self, state: PublishState) -> PublishState:
        """Node: Generate GitHub Actions workflow."""
        slog = logger.bind(phase="generate_workflow")
        slog.info("Generating GitHub Actions workflow")

        file_path = (
            "publish_results/.github/workflows/"
            "ansible-collection-import.yml"
        )

        result = generate_github_actions_workflow(
            file_path=file_path
        )
        if result.startswith("ERROR"):
            state.failed = True
            state.failure_reason = result
            state.publish_output = result
            return state

        state.workflow_generated = True
        slog.info("GitHub Actions workflow generated successfully")
        return state

    def _verify_files_node(self, state: PublishState) -> PublishState:
        """Node: Verify all required files exist."""
        slog = logger.bind(phase="verify_files")
        slog.info("Verifying files exist")

        required_files = [
            f"publish_results/roles/{state.role}",
            (
                f"publish_results/playbooks/"
                f"{state.role}_deploy.yml"
            ),
            (
                f"publish_results/aap-config/job-templates/"
                f"{state.job_template_name}.yaml"
            ),
            (
                "publish_results/.github/workflows/"
                "ansible-collection-import.yml"
            ),
        ]

        result = verify_files_exist(file_paths=required_files)
        if result.startswith("ERROR"):
            state.failed = True
            state.failure_reason = result
            state.publish_output = result
            return state

        state.files_verified = True
        slog.info("All files verified successfully")
        return state

    def _commit_changes_node(self, state: PublishState) -> PublishState:
        """Node: Commit changes to git."""
        slog = logger.bind(phase="commit_changes")
        slog.info("Committing changes to git")

        repository_url = state.github_repository_url
        directory = "publish_results"
        commit_message = (
            f"Add {state.role} role and related configurations"
        )

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

        result = github_commit_changes(
            repository_url=repository_url,
            directory=directory,
            commit_message=commit_message,
            branch=branch,
        )
        if result.startswith("ERROR"):
            state.failed = True
            state.failure_reason = result
            state.publish_output = result
            return state

        state.changes_committed = True
        slog.info("Changes committed successfully")
        return state

    def _push_branch_node(self, state: PublishState) -> PublishState:
        """Node: Push branch to remote."""
        slog = logger.bind(phase="push_branch")
        slog.info("Pushing branch to remote")

        repository_url = state.github_repository_url
        branch = state.pr_head_branch
        repo_path = Path(state.repo_path) if state.repo_path else None

        result = github_push_branch(
            repository_url=repository_url,
            branch=branch,
            repo_path=repo_path,
            remote="origin",
            force=False,
        )
        if result.startswith("ERROR"):
            state.failed = True
            state.failure_reason = result
            state.publish_output = result
            return state

        state.branch_pushed = True
        slog.info("Branch pushed successfully")
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

        result = github_create_pr(
            repository_url=repository_url,
            title=title,
            body=body,
            head=head,
            base=base,
        )
        if result.startswith("ERROR"):
            state.failed = True
            state.failure_reason = result
            state.publish_output = result
            return state

        # Extract PR URL from result if available
        if "URL:" in result:
            pr_url = result.split("URL:")[-1].strip()
            state.pr_url = pr_url

        state.pr_created = True
        state.publish_output = result
        slog.info("Pull Request created successfully")
        return state

    def _check_verification(
        self, state: PublishState
    ) -> Literal["commit_changes", "mark_failed", "__end__"]:
        """Conditional edge: Check if verification passed."""
        if state.failed:
            return "mark_failed"
        if state.skip_git:
            return "__end__"
        return "commit_changes"

    def _check_git_complete(
        self, state: PublishState
    ) -> Literal["__end__", "mark_failed"]:
        """Conditional edge: Check if git steps completed successfully."""
        if state.failed:
            return "mark_failed"
        return "__end__"

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
            result = self._graph.invoke(
                initial_state, config=get_runnable_config()
            )
            final_state = PublishState(**result)

            if final_state.failed:
                slog.error(
                    f"Publish failed for role {final_state.role}: "
                    f"{final_state.failure_reason or 'Unknown error'}"
                )
            else:
                if final_state.skip_git:
                    slog.info(
                        f"Publish completed successfully for role "
                        f"{final_state.role}! "
                        f"(Git steps skipped - files in publish_results/)"
                    )
                else:
                    slog.info(
                        f"Publish completed successfully for role "
                        f"{final_state.role}!"
                    )
                    if final_state.pr_url:
                        slog.info(f"PR URL: {final_state.pr_url}")

            return final_state

        except Exception as e:
            error_str = str(e)
            slog.error(f"Error in PublishWorkflow: {error_str}")
            slog.debug(f"Full traceback: {traceback.format_exc()}")

            initial_state.failed = True
            initial_state.failure_reason = (
                f"Publish workflow error: {error_str}"
            )
            initial_state.publish_output = (
                f"ERROR: Unexpected error occurred. "
                f"Error details: {error_str}"
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
                  Files will be created in publish_results/ only.

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
    )
    result = publish_workflow.invoke(initial_state)

    if result.failed:
        failure_reason = result.failure_reason or "Unknown error"
        logger.error(f"Publish failed for role {role_name}: {failure_reason}")
    else:
        logger.info(f"Publish completed successfully for role {role_name}!")

    return result
