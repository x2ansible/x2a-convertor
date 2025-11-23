# Publisher Workflow Documentation

This document describes the publisher workflow for publishing Ansible roles to GitHub using GitOps approach.

## Overview

The publisher workflow (`src/publishers/publish.py`) automates the process of:

1. Finding the ansible code needed to upload
2. Generating directory structure for PR
3. Adding the ansible code to that directory in the specific tree (roles, templates etc)
4. Generating a playbook that uses the role (REQUIRED)
5. Generating a job template that references the playbook (REQUIRED)
6. Generating GitHub Actions workflow for GitOps
7. Verifying all generated files exist in the publish_results/ directory
8. Committing changes to git
9. Pushing branch to remote
10. Creating a Pull Request for the publish_results/ directory to the GitHub repository

The workflow uses a LangGraph react agent that autonomously decides which tools to use based on the task description.

## Workflow Steps

### 1. Find Ansible Code

**Purpose:** Locate and validate the Ansible role/module that needs to be published.

**Actions:**

- Use file system tools (`list_directory`, `file_search`, `read_file`) to locate the ansible code
- Verify the role path exists and contains valid Ansible role structure
- Identify all files and directories that need to be included

**Tools Used:**

- `FileSearchTool`: Search for files in the role directory
- `ListDirectoryTool`: List directory contents to verify role structure
- `ReadFileTool`: Read files to validate role contents

### 2. Generate Directory Structure for PR

**Purpose:** Create the GitOps repository structure where the ansible code will be organized.

**Actions:**

- Create directories for roles, playbooks, and AAP configs
- Set up the proper tree structure (roles/, templates/, etc.)

**Tool Used:** `CreateDirectoryStructureTool`

**Parameters:**

- `base_path`: Base path where directories should be created
- `structure`: List of directory paths to create

### 3. Add Ansible Code to Directory

**Purpose:** Copy the ansible code to the repository structure in the correct tree.

**Actions:**

- Copy the role directory to the new location
- Preserve the complete role structure (tasks/, handlers/, templates/, etc.)
- Ensure all ansible code is properly organized

**Tool Used:** `CopyRoleDirectoryTool`

**Parameters:**

- `source_role_path`: Source path to the Ansible role directory
- `destination_path`: Destination path where the role should be copied

### 4. Generate Playbook (REQUIRED)

**Purpose:** Generate an Ansible playbook that uses the role.

**Actions:**

- Generate a playbook YAML file that references the role
- Save to `publish_results/playbooks/{role_name}_deploy.yml`

**Tool Used:** `GeneratePlaybookYAMLTool`

**Parameters:**

- `file_path`: Path to save playbook (must include `publish_results/` prefix)
- `name`: Playbook name
- `role_name`: Name of the role to use
- `hosts`: Target hosts (optional, default: 'all')
- `become`: Use privilege escalation (optional, default: false)
- `vars`: Additional variables (optional, default: {})

### 5. Generate Job Template (REQUIRED)

**Purpose:** Generate an AAP job template that references the playbook.

**Actions:**

- Generate a job template YAML file for Ansible Automation Platform
- Save to `publish_results/aap-config/job-templates/{job_template_name}.yaml`

**Tool Used:** `GenerateJobTemplateYAMLTool`

**Parameters:**

- `file_path`: Path to save job template (must include `publish_results/` prefix)
- `name`: Job template name
- `playbook_path`: Relative path to playbook (e.g., `playbooks/{role_name}_deploy.yml`)
- `inventory`: Inventory name or path
- `role_name`: Role name (optional)
- `description`: Template description (optional)
- `extra_vars`: Additional variables (optional)

### 6. Generate GitHub Actions Workflow

**Purpose:** Generate a GitHub Actions workflow for GitOps sync to AAP.

**Actions:**

- Generate a workflow file for Ansible Collection Import to AAP
- Save to `publish_results/.github/workflows/ansible-collection-import.yml`

**Tool Used:** `GenerateGitHubActionsWorkflowTool`

**Parameters:**

- `file_path`: Path to save workflow (must include `publish_results/` prefix)
- `collection_namespace`: Collection namespace (optional)
- `collection_name`: Collection name (optional)

### 7. Verify Generated Files

**Purpose:** Verify all generated files exist before committing.

**Actions:**

- Use `list_directory` to verify directory structure in `publish_results/`
- Verify role was copied to `publish_results/roles/{role_name}/`
- Verify playbook exists at `publish_results/playbooks/{role_name}_deploy.yml`
- Verify job template exists at `publish_results/aap-config/job-templates/{job_template_name}.yaml`
- Verify GitHub Actions workflow exists at `publish_results/.github/workflows/ansible-collection-import.yml`

**Tools Used:**

- `ListDirectoryTool`: Verify directory structure

### 8. Commit Changes to Git

**Purpose:** Commit all changes to a feature branch in the target repository.

**Actions:**

- Clone the target repository
- Copy the `publish_results/` directory to the repository
- Create a feature branch (e.g., `publish-{role_name}`)
- Stage and commit all changes

**Tool Used:** `GitHubCommitChangesTool`

**Parameters:**

- `repository_url`: GitHub repository URL
- `commit_message`: Descriptive commit message
- `branch`: Feature branch name
- `directory`: Directory to commit (default: 'publish_results')

### 9. Push Branch to Remote

**Purpose:** Push the feature branch to the remote repository.

**Actions:**

- Push the branch to the remote repository
- Ensure branch exists in remote before creating PR

**Tool Used:** `GitHubPushBranchTool`

**Parameters:**

- `repository_url`: GitHub repository URL
- `branch`: Branch name to push
- `remote`: Remote name (optional, default: 'origin')
- `force`: Force push (optional, default: False)

### 10. Create Pull Request

**Purpose:** Create a PR with all the changes for review.

**Actions:**

- Create a PR from the feature branch to the base branch
- Include a clear title and description about GitOps sync to AAP

**Tool Used:** `GitHubCreatePRTool`

**Parameters:**

- `repository_url`: GitHub repository URL
- `title`: PR title
- `body`: PR description/body
- `head`: Branch name containing the changes (source branch)
- `base`: Branch name to merge into (target branch, default: "main")

**Environment Variables:**

- `GITHUB_TOKEN`: GitHub personal access token for authentication (required)

## State Structure

The `PublishState` TypedDict contains:

```python
{
    "user_message": str,
    "path": str,
    "role": str,                   # Role name
    "role_path": str,              # Path to role directory
    "github_repository_url": str,  # GitHub repo URL
    "github_branch": str,          # Branch to push to
    "role_registered": bool,       # Whether role was registered
    "job_template_name": str,       # Generated job template name
    "job_template_created": bool,  # Whether template was created
    "publish_output": str,         # Final output message
    "failed": bool,                # Whether workflow failed
    "failure_reason": str,         # Error message if failed
}
```

## Tools

### File System Tools

- `FileSearchTool`: Search for files in the role directory
- `ListDirectoryTool`: List directory contents to verify role structure
- `ReadFileTool`: Read files to validate role contents

### Directory Structure Tools

- `CreateDirectoryStructureTool`: Create directory structure for GitOps
  - **File:** `tools/create_directory_structure.py`
  - Creates all specified directories, creating parent directories as needed

### Role Management Tools

- `CopyRoleDirectoryTool`: Copy an entire Ansible role directory
  - **File:** `tools/copy_role_directory.py`
  - Recursively copies all files and subdirectories preserving the complete role structure

### Configuration Generation Tools

- `GeneratePlaybookYAMLTool`: Generate a playbook YAML that uses the role (REQUIRED)
  - **File:** `tools/generate_playbook_yaml.py`
  - Must be generated before job template (job template references playbook)
- `GenerateJobTemplateYAMLTool`: Generate AAP job template YAML configuration (REQUIRED)
  - **File:** `tools/generate_job_template_yaml.py`
- `GenerateGitHubActionsWorkflowTool`: Generate GitHub Actions workflow for GitOps
  - **File:** `tools/generate_github_actions_workflow.py`
  - Creates workflow for Ansible Collection Import to AAP

### GitHub Tools

- `GitHubCommitChangesTool`: Commit changes to git repository
  - **File:** `tools/github_commit_changes.py`
  - Clones repository, copies directory, creates branch, and commits
  - Must be used before pushing
- `GitHubPushBranchTool`: Push a git branch to remote repository
  - **File:** `tools/github_push_branch.py`
  - Pushes branch to remote (must be used before creating PR)
- `GitHubCreatePRTool`: Create a Pull Request in GitHub
  - **File:** `tools/github_create_pr.py`
  - Creates a PR from a branch to the base branch in a GitHub repository
  - Requires branch to exist in remote (use `github_push_branch` first)
  - Requires `GITHUB_TOKEN` environment variable for authentication

## Usage

```python
from src.publishers.publish import publish_role

# Publish a role
result = publish_role(
    role_name="my_role",
    role_path="ansible/my_role",
    github_repository_url="https://github.com/your-org/ansible-roles.git",
    github_branch="main"
)

if result["failed"]:
    print(f"Failed: {result['failure_reason']}")
else:
    print(result["publish_output"])
```

## Environment Variables Summary

### GitHub

- `GITHUB_REPOSITORY_URL`: Repository URL (passed as parameter)
- `GITHUB_BRANCH`: Branch name (passed as parameter, defaults to "main")
- `GITHUB_TOKEN`: Authentication token (required for creating PR)

## Implementation Notes

### Repository Structure

**IMPORTANT: All files must be created in the `publish_results/` directory at the root level.**

The final structure in `publish_results/` should look like:

```
publish_results/
├── .github/
│   └── workflows/
│       └── ansible-collection-import.yml  # GitHub Actions workflow
├── roles/
│   └── {role_name}/          # Copied role directory
│       ├── tasks/
│       ├── handlers/
│       ├── templates/
│       ├── meta/
│       └── ...
├── playbooks/               # REQUIRED: playbook files
│   └── {role_name}_deploy.yml
└── aap-config/              # REQUIRED: AAP configuration files
    ├── job-templates/
    │   └── {job_template_name}.yaml  # REQUIRED: job template
    └── inventories/         # Optional: inventory files
        └── webservers-production.yaml
```

This entire `publish_results/` directory will be pushed to GitHub as the PR content.

### Error Handling

The workflow includes comprehensive error handling:

- Each step checks for previous failures
- Errors are logged and stored in state
- Workflow stops on first failure
- Final state includes failure reason if failed
- Errors are detected by checking if "ERROR" appears in the output content
- Exception details are logged for debugging

### Workflow Order

The workflow order is critical:

1. **Verify → Commit → Push → Create PR**: Files must be verified before committing, branch must be committed before pushing, branch must be pushed before creating PR
2. **Playbook before Job Template**: The playbook must be generated before the job template (job template references the playbook)
3. **All steps are required**: The agent must complete all 10 steps, including verification, commit, push, and PR creation

### LangGraph React Agent

The publisher uses a LangGraph react agent pattern where:

- The LLM autonomously decides which tools to use
- Tools are called based on the task description
- The agent follows the workflow defined in the system prompt
- All operations are performed via tools, ensuring traceability
