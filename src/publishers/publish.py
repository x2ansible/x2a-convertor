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
    generate_ansible_cfg,
    generate_collections_requirements,
    generate_inventory_file,
    generate_playbook_yaml,
    github_commit_changes,
    github_create_repository,
    github_push_branch,
    load_collections_file,
    load_inventory_file,
    sync_to_aap,
    verify_files_exist,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PublishState:
    """State for the publish workflow."""

    path: str
    roles: list[str]  # List of role names
    role_paths: list[str]  # List of role paths corresponding to roles
    github_owner: str
    github_branch: str
    github_repository_url: str = ""  # Set after repository creation
    publish_output: str = ""
    failed: bool = False
    failure_reason: str = ""
    # Workflow tracking (only flags used in summary/conditionals)
    branch_pushed: bool = False
    repository_created: bool = False
    skip_git: bool = False
    repo_path: str = ""
    publish_dir: str = ""
    collections: list[dict[str, str]] | None = None
    inventory: dict | None = None
    # AAP integration (optional, env-driven)
    aap_enabled: bool = False
    aap_project_name: str = ""
    aap_project_id: int | None = None
    aap_project_update_id: int | None = None
    aap_project_update_status: str = ""
    aap_error: str = ""


class PublishWorkflow:
    """Implements a publishing workflow for Ansible roles using deterministic
    processes and LangGraph.

    Steps:
    1. Create ansible project (directory structure, copy roles,
       generate playbooks, ansible.cfg, collections/requirements.yml)
    2. Verify files exist
    3. Create GitHub repository (if not skip_git)
    4. Commit changes (if not skip_git)
    5. Push branch (if not skip_git)
    6. Display summary
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
        workflow.add_node("create_ansible_project", self._create_ansible_project_node)
        workflow.add_node("verify_files", self._verify_files_node)
        workflow.add_node("create_repository", self._create_repository_node)
        workflow.add_node("commit_changes", self._commit_changes_node)
        workflow.add_node("push_branch", self._push_branch_node)
        workflow.add_node("sync_to_aap", self._sync_to_aap)
        workflow.add_node("summary", self._summary_node)
        workflow.add_node("mark_failed", self._mark_failed_node)

        workflow.add_edge(START, "create_ansible_project")
        workflow.add_edge("create_ansible_project", "verify_files")
        workflow.add_conditional_edges("verify_files", self._check_verification)
        workflow.add_edge("create_repository", "commit_changes")
        workflow.add_conditional_edges(
            "commit_changes",
            self._check_commit_result,
        )
        workflow.add_edge("push_branch", "sync_to_aap")
        workflow.add_edge("sync_to_aap", "summary")
        workflow.add_edge("summary", END)
        workflow.add_edge("mark_failed", "summary")

        return workflow.compile()

    def _create_ansible_project_node(
        self,
        state: PublishState,
    ) -> PublishState:
        """Node: Create complete Ansible project structure.

        Creates:
        - Directory structure (collections/, inventory/, roles/,
          playbooks/)
        - Copies all role directories
        - Generates wrapper playbooks for each role (run_role_X.yml)
        - Generates ansible.cfg
        - Generates collections/requirements.yml
        - Generates inventory/hosts.yml
        """
        slog = logger.bind(phase="create_ansible_project")
        slog.info("Creating Ansible project structure")

        base_path = state.publish_dir

        try:
            # 1. Create directory structure
            structure = [
                "collections",
                "inventory",
                "roles",
                "playbooks",
            ]
            create_directory_structure(
                base_path=base_path,
                structure=structure,
            )
            slog.info("Directory structure created")

            # 2. Copy all role directories
            for role_name, role_path in zip(
                state.roles,
                state.role_paths,
                strict=True,
            ):
                destination_path = f"{base_path}/roles/{role_name}"
                slog.info(f"Copying role {role_name} from {role_path}")
                copy_role_directory(
                    source_role_path=role_path,
                    destination_path=destination_path,
                )
            slog.info("All roles copied successfully")

            # 3. Generate wrapper playbooks for each role
            for role_name in state.roles:
                file_path = f"{base_path}/playbooks/run_{role_name}.yml"
                name = f"Run {role_name}"
                slog.info(f"Generating playbook for {role_name}")
                generate_playbook_yaml(
                    file_path=file_path,
                    name=name,
                    role_name=role_name,
                )
            slog.info("All playbooks generated successfully")

            # 4. Generate ansible.cfg
            ansible_cfg_path = f"{base_path}/ansible.cfg"
            slog.info("Generating ansible.cfg")
            generate_ansible_cfg(ansible_cfg_path)

            # 5. Generate collections/requirements.yml
            collections_req_path = f"{base_path}/collections/requirements.yml"
            slog.info("Generating collections/requirements.yml")
            generate_collections_requirements(
                collections_req_path, collections=state.collections
            )

            # 6. Generate inventory file
            inventory_path = f"{base_path}/inventory/hosts.yml"
            slog.info("Generating inventory file")
            generate_inventory_file(inventory_path, inventory=state.inventory)

            slog.info("Ansible project created successfully")
        except (ValueError, FileNotFoundError, OSError, RuntimeError) as e:
            state.failed = True
            state.failure_reason = str(e)
            slog.error(f"Failed to create Ansible project: {e}")
        return state

    def _get_required_files(self, state: PublishState) -> list[str]:
        """Get list of required files to verify.

        This method can be overridden to customize which files are required.

        Args:
            state: Current publish state

        Returns:
            List of file paths to verify
        """
        required_files = [
            f"{state.publish_dir}/ansible.cfg",
            f"{state.publish_dir}/collections/requirements.yml",
            f"{state.publish_dir}/inventory/hosts.yml",
        ]
        # Add role directories and playbooks for each role
        for role_name in state.roles:
            required_files.append(f"{state.publish_dir}/roles/{role_name}")
            required_files.append(f"{state.publish_dir}/playbooks/run_{role_name}.yml")
        return required_files

    def _verify_files_node(self, state: PublishState) -> PublishState:
        """Node: Verify all required files exist."""
        slog = logger.bind(phase="verify_files")
        slog.info("Verifying files exist")

        required_files = self._get_required_files(state)

        try:
            verify_files_exist(file_paths=required_files)
            slog.info("All files verified successfully")
        except FileNotFoundError as e:
            state.failed = True
            state.failure_reason = str(e)
        return state

    def _create_repository_node(self, state: PublishState) -> PublishState:
        """Node: Create GitHub repository."""
        slog = logger.bind(phase="create_repository")
        slog.info("Creating GitHub repository")

        owner = state.github_owner
        # Use first role name or a generic name for multi-role projects
        if len(state.roles) == 1:
            repo_name = f"{state.roles[0]}-gitops"
            description = (
                f"GitOps repository for {state.roles[0]} Ansible role deployment"
            )
        else:
            repo_name = "ansible-project-gitops"
            role_list = ", ".join(state.roles)
            description = (
                f"GitOps repository for Ansible project with roles: {role_list}"
            )

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
            state.failure_reason = (
                f"Repository creation validation failed: {e}. "
                "Check your GITHUB_TOKEN and owner configuration."
            )
        except requests.exceptions.HTTPError as e:
            state.failed = True
            state.failure_reason = (
                f"GitHub API error: {e}. "
                "This might be a rate limit or permission issue."
            )
        except requests.exceptions.RequestException as e:
            state.failed = True
            state.failure_reason = f"GitHub API request failed: {e}"
        except RuntimeError as e:
            state.failed = True
            state.failure_reason = str(e)
        return state

    def _commit_changes_node(self, state: PublishState) -> PublishState:
        """Node: Commit changes to git."""
        slog = logger.bind(phase="commit_changes")
        slog.info("Committing changes to git")

        repository_url = state.github_repository_url
        # Resolve to absolute path to ensure it's found regardless of cwd
        directory = str(Path(state.publish_dir).resolve())
        slog.info(f"Committing deployment directory: {directory}")
        if len(state.roles) == 1:
            commit_message = f"Add {state.roles[0]} role and related configurations"
        else:
            role_list = ", ".join(state.roles)
            commit_message = f"Add Ansible project with roles: {role_list}"

        # For new repository, push directly to the specified branch
        # (usually main)
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
            slog.info(f"Changes committed successfully. Commit: {commit_hash}")
        except ValueError as e:
            # Validation errors are user input issues - provide clear feedback
            state.failed = True
            state.failure_reason = (
                f"Validation failed: {e}. "
                "Please check your repository URL, branch, and directory."
            )
        except FileNotFoundError as e:
            state.failed = True
            state.failure_reason = f"Directory not found: {e}"
        except subprocess.CalledProcessError as e:
            # Git errors might be retryable or need different handling
            state.failed = True
            state.failure_reason = (
                f"Git operation failed: {e}. "
                "This might be a temporary issue - you can try again."
            )
        except RuntimeError as e:
            # All RuntimeErrors are failures
            state.failed = True
            state.failure_reason = str(e)
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
            state.failure_reason = (
                f"Configuration error: {e}. "
                "This should not happen if previous steps succeeded."
            )
        except FileNotFoundError as e:
            state.failed = True
            state.failure_reason = f"Repository not found: {e}"
        except subprocess.CalledProcessError as e:
            # Git push failures - might be auth, network, or conflict issues
            state.failed = True
            state.failure_reason = (
                f"Failed to push branch: {e}. "
                "Check your authentication and network connection."
            )
        except RuntimeError as e:
            state.failed = True
            state.failure_reason = str(e)
        return state

    def _sync_to_aap(self, state: PublishState) -> PublishState:
        """Node: Upsert an AAP Project for the pushed GitHub repository.

        Failures here are reported in the summary but do not fail the publish.
        """
        slog = logger.bind(phase="sync to aap")

        should_skip = state.failed or state.skip_git or (not state.branch_pushed)
        if should_skip:
            return state

        repository_url = state.github_repository_url
        branch = state.github_branch

        tool_result = sync_to_aap(repository_url=repository_url, branch=branch)
        state.aap_enabled = bool(tool_result.get("enabled"))
        state.aap_project_name = str(tool_result.get("project_name") or "")
        state.aap_project_id = tool_result.get("project_id")
        state.aap_project_update_id = tool_result.get("project_update_id")
        state.aap_project_update_status = str(
            tool_result.get("project_update_status") or ""
        )
        state.aap_error = str(tool_result.get("error") or "")

        if not state.aap_enabled:
            return state

        if state.aap_error:
            slog.error(f"AAP sync failed: {state.aap_error}")
            return state

        slog.info(
            f"AAP project synced: name={state.aap_project_name} "
            f"id={state.aap_project_id} "
            f"update_id={state.aap_project_update_id} "
            f"status={state.aap_project_update_status}"
        )
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
        summary_lines.append(f"  - ansible.cfg: {state.publish_dir}/ansible.cfg")
        summary_lines.append(
            f"  - Collections requirements: "
            f"{state.publish_dir}/collections/requirements.yml"
        )
        summary_lines.append(f"  - Inventory: {state.publish_dir}/inventory/hosts.yml")
        for role_name in state.roles:
            summary_lines.append(f"  - Role: {state.publish_dir}/roles/{role_name}/")
            summary_lines.append(
                f"  - Playbook: {state.publish_dir}/playbooks/run_{role_name}.yml"
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

        # AAP integration summary (sync_to_aap node writes these fields)
        summary_lines.append("\nAAP Integration:")
        if state.failed:
            summary_lines.append("  Not attempted (publish failed).")
        elif state.skip_git:
            summary_lines.append("  Not attempted (skip_git=true).")
        elif not state.branch_pushed:
            summary_lines.append("  Not attempted (branch was not pushed).")
        elif not state.aap_enabled:
            summary_lines.append("  Disabled (AAP not configured).")
        elif state.aap_error:
            summary_lines.append("  Result: FAILED")
            summary_lines.append(f"  Error: {state.aap_error}")
        else:
            summary_lines.append("  Result: SUCCESS")
            if state.aap_project_name:
                summary_lines.append(f"  Project: {state.aap_project_name}")
            if state.aap_project_id is not None:
                summary_lines.append(f"  Project ID: {state.aap_project_id}")
            if state.aap_project_update_id is not None:
                summary_lines.append(f"  Sync job ID: {state.aap_project_update_id}")
            if state.aap_project_update_status:
                summary_lines.append(
                    f"  Sync job status: {state.aap_project_update_status}"
                )

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
                role_list = ", ".join(final_state.roles)
                slog.error(
                    f"Publish failed for roles {role_list}: "
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
            initial_state.failure_reason = (
                f"Publish workflow error: {error_str}. Unexpected error occurred."
            )
            return initial_state


def publish_role(
    role_name: str | list[str],
    role_path: str | list[str],
    github_owner: str,
    github_branch: str,
    base_path: str | None = None,
    skip_git: bool = False,
    collections_file: str | Path | None = None,
    inventory_file: str | Path | None = None,
    collections: list[dict[str, str]] | None = None,
    inventory: dict | None = None,
) -> PublishState:
    """Publish one or more roles to GitHub.

    Optionally registers the created/pushed Git repository as an AAP Project
    (env-driven; see docs).

    Args:
        role_name: Name(s) of the role(s) to publish (string or list)
        role_path: Path(s) to the role directory(ies) (string or list)
            (e.g., <path>/ansible/roles/{role})
        github_owner: GitHub user or organization name
        github_branch: Branch name to push to (default: main)
        base_path: Base path for constructing deployment path
            (defaults to parent of role_path's parent)
        skip_git: If True, skip git steps (create repo, commit, push).
                  Files will be created in a role-specific directory.
        collections_file: Path to YAML/JSON collections file. If provided and
            collections is None, collections will be loaded from this file.
        inventory_file: Path to YAML/JSON inventory file. If provided and
            inventory is None, inventory will be loaded from this file.
        collections: List of collection dicts with 'name' and optional
            'version'
            Example: [{"name": "community.general", "version": ">=1.0.0"}]
        inventory: Inventory structure as dict. If None, uses sample inventory.
            Example: {"all": {"children": {"servers": {"hosts": {...}}}}}

    Returns:
        PublishState with results
    """
    # Normalize to lists
    role_names = [role_name] if isinstance(role_name, str) else role_name

    role_paths = [role_path] if isinstance(role_path, str) else role_path

    if collections is None and collections_file:
        collections = load_collections_file(collections_file)

    if inventory is None and inventory_file:
        inventory = load_inventory_file(inventory_file)

    if len(role_names) != len(role_paths):
        error_msg = (
            f"Number of role names ({len(role_names)}) must match "
            f"number of role paths ({len(role_paths)})"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    role_list = ", ".join(role_names)
    logger.info(f"Publishing {len(role_names)} role(s): {role_list}")

    # Determine base path and construct deployment path
    # Use first role path to determine base
    first_role_path_obj = Path(role_paths[0])
    if base_path:
        base_path_obj = Path(base_path)
        # For multi-role projects, use a generic name
        if len(role_names) == 1:
            deployment_path = base_path_obj / "ansible" / "deployments" / role_names[0]
        else:
            deployment_path = (
                base_path_obj / "ansible" / "deployments" / "ansible-project"
            )
    else:
        # Extract ansible path from role_path:
        # <path>/ansible/roles/{role} -> <path>/ansible
        ansible_path = first_role_path_obj.parent.parent
        # Construct deployment path at same level as roles/
        if len(role_names) == 1:
            deployment_path = ansible_path / "deployments" / role_names[0]
        else:
            deployment_path = ansible_path / "deployments" / "ansible-project"
        base_path_obj = ansible_path.parent

    # Run the publish workflow
    publish_workflow = PublishWorkflow()
    initial_state = PublishState(
        path=str(base_path_obj),
        roles=role_names,
        role_paths=role_paths,
        github_owner=github_owner,
        github_branch=github_branch,
        skip_git=skip_git,
        publish_dir=str(deployment_path),
        collections=collections,
        inventory=inventory,
    )
    result = publish_workflow.invoke(initial_state)

    if result.failed:
        failure_reason = result.failure_reason or "Unknown error"
        logger.error(f"Publish failed for role(s) {role_list}: {failure_reason}")
        return result

    logger.info(f"Publish completed successfully for role(s) {role_list}!")
    return result
