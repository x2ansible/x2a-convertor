"""Tests for GitHub operations in the publisher workflow (publish.py flow).

These tests mock the high-level tool functions (github_create_repository,
github_commit_changes, github_push_branch) since they are covered by
test_tools_github.py. We verify the publish workflow orchestrates them correctly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import ANY

import requests

from src.publishers.publish import publish_role
from src.publishers.tools import AAPSyncResult


def test_publish_role_github_happy_flow_single_role(
    mocker,
    tmp_path,
    sample_role_dir,
):
    """Test successful single role publish flow with all git operations."""
    mock_create_repo = mocker.patch(
        "src.publishers.publish.github_create_repository",
        return_value="https://github.com/test/sample_role-gitops.git",
    )
    mock_commit = mocker.patch(
        "src.publishers.publish.github_commit_changes",
        return_value="abc1234",
    )
    mock_push = mocker.patch(
        "src.publishers.publish.github_push_branch",
        return_value=None,
    )
    mock_sync_aap = mocker.patch(
        "src.publishers.publish.sync_to_aap",
        return_value=AAPSyncResult.disabled(),
    )

    result = publish_role(
        role_name="sample_role",
        role_path=sample_role_dir,
        github_owner="test",
        github_branch="main",
        base_path=str(tmp_path),
        skip_git=False,
    )

    # Verify result state
    assert result.failed is False
    assert result.repository_created is True
    assert result.branch_pushed is True
    assert (
        result.github_repository_url == "https://github.com/test/sample_role-gitops.git"
    )
    assert "PUBLISH SUMMARY" in result.publish_output

    # Verify github_create_repository was called with correct args
    mock_create_repo.assert_called_once_with(
        owner="test",
        repo_name="sample_role-gitops",
        description="GitOps repository for sample_role Ansible role deployment",
        private=False,
    )

    # Verify github_commit_changes was called and inspect the directory contents
    mock_commit.assert_called_once()
    commit_call_kwargs = mock_commit.call_args.kwargs
    assert (
        commit_call_kwargs["repository_url"]
        == "https://github.com/test/sample_role-gitops.git"
    )
    assert commit_call_kwargs["branch"] == "main"
    assert "sample_role" in commit_call_kwargs["commit_message"]

    # Verify the directory passed to commit contains expected files
    dir_path = Path(commit_call_kwargs["directory"])
    assert dir_path.exists()
    assert (dir_path / "ansible.cfg").exists()
    assert (dir_path / "collections" / "requirements.yml").exists()
    assert (dir_path / "inventory" / "hosts.yml").exists()
    assert (dir_path / "roles" / "sample_role").exists()
    assert (dir_path / "playbooks" / "run_sample_role.yml").exists()

    # Verify github_push_branch was called with correct args
    mock_push.assert_called_once_with(
        repository_url="https://github.com/test/sample_role-gitops.git",
        branch="main",
        repo_path=ANY,
        remote="origin",
        force=False,
    )

    # Verify sync_to_aap was called
    mock_sync_aap.assert_called_once_with(
        repository_url="https://github.com/test/sample_role-gitops.git",
        branch="main",
    )


def test_publish_role_github_repo_create_http_error_fails(
    mocker,
    tmp_path,
    sample_role_dir,
):
    """Test that HTTPError during repo creation results in failed state."""
    mock_create_repo = mocker.patch(
        "src.publishers.publish.github_create_repository",
        side_effect=requests.exceptions.HTTPError("boom"),
    )

    result = publish_role(
        role_name="sample_role",
        role_path=sample_role_dir,
        github_owner="test",
        github_branch="main",
        base_path=str(tmp_path),
        skip_git=False,
    )

    assert result.failed is True
    assert "GitHub API error" in (result.failure_reason or "")
    assert "PUBLISH FAILED" in result.publish_output

    # Verify create_repo was called (and failed)
    mock_create_repo.assert_called_once()


def test_publish_role_github_commit_failure_fails(
    mocker,
    tmp_path,
    sample_role_dir,
):
    """Test that CalledProcessError during commit results in failed state."""
    mocker.patch(
        "src.publishers.publish.github_create_repository",
        return_value="https://github.com/test/sample_role-gitops.git",
    )
    mock_commit = mocker.patch(
        "src.publishers.publish.github_commit_changes",
        side_effect=subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "commit"],
            stderr="nope",
        ),
    )

    result = publish_role(
        role_name="sample_role",
        role_path=sample_role_dir,
        github_owner="test",
        github_branch="main",
        base_path=str(tmp_path),
        skip_git=False,
    )

    assert result.failed is True
    assert "Git operation failed" in (result.failure_reason or "")
    assert "PUBLISH FAILED" in result.publish_output

    # Verify commit was called (and failed)
    mock_commit.assert_called_once()


def test_publish_role_github_push_failure_fails(
    mocker,
    tmp_path,
    sample_role_dir,
):
    """Test that CalledProcessError during push results in failed state."""
    mocker.patch(
        "src.publishers.publish.github_create_repository",
        return_value="https://github.com/test/sample_role-gitops.git",
    )
    mocker.patch(
        "src.publishers.publish.github_commit_changes",
        return_value="abc1234",
    )
    mock_push = mocker.patch(
        "src.publishers.publish.github_push_branch",
        side_effect=subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "push"],
            stderr="permission denied",
        ),
    )

    result = publish_role(
        role_name="sample_role",
        role_path=sample_role_dir,
        github_owner="test",
        github_branch="main",
        base_path=str(tmp_path),
        skip_git=False,
    )

    assert result.failed is True
    assert "Failed to push branch" in (result.failure_reason or "")
    assert "PUBLISH FAILED" in result.publish_output

    # Verify push was called (and failed)
    mock_push.assert_called_once()


def test_publish_role_skip_git_does_not_call_github_tools(
    mocker,
    tmp_path,
    sample_role_dir,
):
    """Test that skip_git=True skips all GitHub operations."""
    mock_create_repo = mocker.patch("src.publishers.publish.github_create_repository")
    mock_commit = mocker.patch("src.publishers.publish.github_commit_changes")
    mock_push = mocker.patch("src.publishers.publish.github_push_branch")
    mock_sync_aap = mocker.patch("src.publishers.publish.sync_to_aap")

    result = publish_role(
        role_name="sample_role",
        role_path=sample_role_dir,
        github_owner="test",
        github_branch="main",
        base_path=str(tmp_path),
        skip_git=True,
    )

    assert result.failed is False
    assert result.repository_created is False
    assert result.branch_pushed is False
    assert "PUBLISH SUMMARY" in result.publish_output

    # None of the git operations should be called
    mock_create_repo.assert_not_called()
    mock_commit.assert_not_called()
    mock_push.assert_not_called()
    mock_sync_aap.assert_not_called()
