"""Unit tests for GitHub publishing tools (src.publishers.tools).

These tests validate the behavior of the tool functions themselves by mocking
subprocess, and by using responses to mock GitHub API responses.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import call

import pytest
import requests
import responses

import src.publishers.tools as tools


def test_github_get_repository_returns_none_when_token_missing(mocker):
    """Test github_get_repository returns None when GITHUB_TOKEN is not set."""
    mocker.patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False)
    assert tools.github_get_repository(owner="test", repo_name="repo") is None


@responses.activate
def test_github_get_repository_returns_clone_url_when_found(mocker):
    """Test github_get_repository returns clone URL when repository exists."""
    mocker.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}, clear=False)

    responses.add(
        responses.GET,
        "https://api.github.com/repos/test/repo",
        json={"clone_url": "https://github.com/test/repo.git"},
        status=200,
    )
    assert (
        tools.github_get_repository(owner="test", repo_name="repo")
        == "https://github.com/test/repo.git"
    )


def test_github_create_repository_returns_existing_repo(mocker):
    """Test github_create_repository returns existing repo URL without creating."""
    mocker.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}, clear=False)

    mock_get_repo = mocker.patch.object(
        tools,
        "github_get_repository",
        return_value="https://github.com/test/repo.git",
    )

    result = tools.github_create_repository(
        owner="test",
        repo_name="repo",
        description="d",
        private=False,
    )

    assert result == "https://github.com/test/repo.git"
    mock_get_repo.assert_called_once_with("test", "repo")


def test_github_create_repository_missing_token_raises(mocker):
    """Test github_create_repository raises ValueError when token is missing."""
    mocker.patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False)
    mocker.patch.object(tools, "github_get_repository", return_value=None)

    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        tools.github_create_repository(
            owner="test",
            repo_name="repo",
            description="d",
            private=False,
        )


def test_github_create_repository_missing_owner_raises(mocker):
    """Test github_create_repository raises ValueError when owner is missing."""
    mocker.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}, clear=False)
    mocker.patch.object(tools, "github_get_repository", return_value=None)

    with pytest.raises(ValueError, match="owner is required"):
        tools.github_create_repository(
            owner="",
            repo_name="repo",
            description="d",
            private=False,
        )


def test_github_create_repository_missing_repo_name_raises(mocker):
    """Test github_create_repository raises ValueError when repo_name is missing."""
    mocker.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}, clear=False)
    mocker.patch.object(tools, "github_get_repository", return_value=None)

    with pytest.raises(ValueError, match="repo_name is required"):
        tools.github_create_repository(
            owner="test",
            repo_name="",
            description="d",
            private=False,
        )


@responses.activate
def test_github_create_repository_org_404_falls_back_to_user_endpoint(mocker):
    """Test github_create_repository falls back to user endpoint when org returns 404."""
    mocker.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}, clear=False)
    mocker.patch.object(tools, "github_get_repository", return_value=None)

    responses.add(
        responses.POST,
        "https://api.github.com/orgs/test/repos",
        json={"message": "not found"},
        status=404,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/user/repos",
        json={
            "clone_url": "https://github.com/test/repo.git",
            "html_url": "https://github.com/test/repo",
        },
        status=201,
    )

    out = tools.github_create_repository(
        owner="test",
        repo_name="repo",
        description="d",
        private=False,
    )

    assert out == "https://github.com/test/repo.git"


@responses.activate
def test_github_create_repository_http_error_raises(mocker):
    """Test github_create_repository raises HTTPError on API failure."""
    mocker.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}, clear=False)
    mocker.patch.object(tools, "github_get_repository", return_value=None)

    responses.add(
        responses.POST,
        "https://api.github.com/orgs/test/repos",
        json={"message": "nope"},
        status=401,
    )

    with pytest.raises(requests.exceptions.HTTPError):
        tools.github_create_repository(
            owner="test",
            repo_name="repo",
            description="d",
            private=False,
        )


@responses.activate
def test_github_create_repository_missing_clone_url_raises(mocker):
    """Test github_create_repository raises RuntimeError when API response lacks clone_url."""
    mocker.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}, clear=False)
    mocker.patch.object(tools, "github_get_repository", return_value=None)

    responses.add(
        responses.POST,
        "https://api.github.com/orgs/test/repos",
        json={"html_url": "x"},
        status=201,
    )

    with pytest.raises(RuntimeError, match="did not return repository URL"):
        tools.github_create_repository(
            owner="test",
            repo_name="repo",
            description="d",
            private=False,
        )


def test_github_commit_changes_directory_missing_raises(tmp_path):
    """Test github_commit_changes raises FileNotFoundError when directory doesn't exist."""
    with pytest.raises(FileNotFoundError, match="does not exist"):
        tools.github_commit_changes(
            repository_url="https://github.com/test/repo.git",
            directory=str(tmp_path / "missing"),
            commit_message="m",
            branch="main",
        )


def test_github_commit_changes_branch_exists_remote_raises(mocker, tmp_path):
    """Test github_commit_changes raises RuntimeError when branch exists remotely."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "file.txt").write_text("x")

    repo_path = tmp_path / "repo"
    mocker.patch.object(tools, "_get_repo_path", return_value=repo_path)
    mocker.patch.object(tools.shutil, "rmtree")
    mocker.patch("os.chdir")

    mock_run = mocker.patch("src.publishers.tools.subprocess.run")
    mock_run.side_effect = [
        # git clone
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git fetch origin
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git ls-remote --heads origin main (branch exists)
        subprocess.CompletedProcess([], 0, stdout="abc\trefs/heads/main\n", stderr=""),
    ]

    with pytest.raises(RuntimeError, match="already exists in repository"):
        tools.github_commit_changes(
            repository_url="https://github.com/test/repo.git",
            directory=str(src_dir),
            commit_message="m",
            branch="main",
        )

    # Verify git commands were constructed correctly
    calls = mock_run.call_args_list
    assert calls[0] == call(
        ["git", "clone", "https://github.com/test/repo.git", str(repo_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert calls[1] == call(
        ["git", "fetch", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert calls[2] == call(
        ["git", "ls-remote", "--heads", "origin", "main"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_github_commit_changes_happy_flow_returns_hash(mocker, tmp_path):
    """Test successful commit flow returns commit hash."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("a")
    (src_dir / "dir").mkdir()
    (src_dir / "dir" / "b.txt").write_text("b")

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    mocker.patch.object(tools, "_get_repo_path", return_value=repo_path)
    mocker.patch.object(tools.shutil, "rmtree")
    mocker.patch("os.chdir")
    mocker.patch.object(tools.shutil, "copytree")
    mocker.patch.object(tools.shutil, "copy2")

    # Mock Path.iterdir to return our source items
    mock_items = [src_dir / "a.txt", src_dir / "dir"]
    mocker.patch.object(Path, "iterdir", return_value=iter(mock_items))

    mock_run = mocker.patch("src.publishers.tools.subprocess.run")
    mock_run.side_effect = [
        # git clone
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git fetch origin
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git ls-remote --heads origin feature (branch doesn't exist)
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git branch --show-current
        subprocess.CompletedProcess([], 0, stdout="main\n", stderr=""),
        # git checkout -b feature
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git add a.txt
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git add dir
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git diff --cached --quiet (returncode=1 means changes exist)
        subprocess.CompletedProcess([], 1, stdout="", stderr=""),
        # git commit -m
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git rev-parse HEAD
        subprocess.CompletedProcess([], 0, stdout="abcdef123456\n", stderr=""),
    ]

    out = tools.github_commit_changes(
        repository_url="https://github.com/test/repo.git",
        directory=str(src_dir),
        commit_message="m",
        branch="feature",
    )

    assert out == "abcdef1"

    # Verify key git commands were called
    mock_run.assert_any_call(
        ["git", "clone", "https://github.com/test/repo.git", str(repo_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    mock_run.assert_any_call(
        ["git", "checkout", "-b", "feature"],
        check=True,
    )
    mock_run.assert_any_call(
        ["git", "commit", "-m", "m"],
        capture_output=True,
        text=True,
        check=True,
    )
    mock_run.assert_any_call(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_github_push_branch_missing_repo_path_raises():
    """Test github_push_branch raises ValueError when repo_path is None."""
    with pytest.raises(ValueError, match="repo_path is required"):
        tools.github_push_branch(
            repository_url="https://github.com/test/repo.git",
            branch="main",
            repo_path=None,
        )


def test_github_push_branch_repo_path_without_git_dir_raises(tmp_path):
    """Test github_push_branch raises FileNotFoundError when .git dir is missing."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    with pytest.raises(FileNotFoundError, match="Repository not found"):
        tools.github_push_branch(
            repository_url="https://github.com/test/repo.git",
            branch="main",
            repo_path=repo_path,
        )


def test_github_push_branch_remote_missing_raises(mocker, tmp_path):
    """Test github_push_branch raises RuntimeError when remote doesn't exist."""
    repo_path = tmp_path / "repo"
    (repo_path / ".git").mkdir(parents=True)

    mocker.patch("os.chdir")

    mock_run = mocker.patch("src.publishers.tools.subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(
        [], 1, stdout="", stderr="no remote"
    )

    with pytest.raises(RuntimeError, match="Remote 'origin' not found"):
        tools.github_push_branch(
            repository_url="https://github.com/test/repo.git",
            branch="main",
            repo_path=repo_path,
            remote="origin",
        )

    mock_run.assert_called_once_with(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_github_push_branch_branch_missing_locally_raises(mocker, tmp_path):
    """Test github_push_branch raises RuntimeError when branch doesn't exist locally."""
    repo_path = tmp_path / "repo"
    (repo_path / ".git").mkdir(parents=True)

    mocker.patch("os.chdir")

    mock_run = mocker.patch("src.publishers.tools.subprocess.run")
    mock_run.side_effect = [
        # git remote get-url origin (success)
        subprocess.CompletedProcess([], 0, stdout="x\n", stderr=""),
        # git fetch origin
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git branch --list main (empty - branch doesn't exist locally)
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
    ]

    with pytest.raises(RuntimeError, match="does not exist locally"):
        tools.github_push_branch(
            repository_url="https://github.com/test/repo.git",
            branch="main",
            repo_path=repo_path,
            remote="origin",
        )

    # Verify the git commands were called correctly
    calls = mock_run.call_args_list
    assert calls[0] == call(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert calls[1] == call(
        ["git", "fetch", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert calls[2] == call(
        ["git", "branch", "--list", "main"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_github_push_branch_happy_flow(mocker, tmp_path):
    """Test successful push flow for a new branch."""
    repo_path = tmp_path / "repo"
    (repo_path / ".git").mkdir(parents=True)

    mocker.patch("os.chdir")

    mock_run = mocker.patch("src.publishers.tools.subprocess.run")
    mock_run.side_effect = [
        # git remote get-url origin
        subprocess.CompletedProcess(
            [], 0, stdout="https://github.com/test/repo.git\n", stderr=""
        ),
        # git fetch origin
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git branch --list feature (exists locally)
        subprocess.CompletedProcess([], 0, stdout="  feature\n", stderr=""),
        # git ls-remote --heads origin feature (doesn't exist remotely)
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git rev-list --count origin/main..feature
        subprocess.CompletedProcess([], 0, stdout="1\n", stderr=""),
        # git push -u origin feature
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
    ]

    tools.github_push_branch(
        repository_url="https://github.com/test/repo.git",
        branch="feature",
        repo_path=repo_path,
        remote="origin",
    )

    # Verify push command was called with -u for new branch
    mock_run.assert_any_call(
        ["git", "push", "-u", "origin", "feature"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_github_push_branch_existing_remote_branch(mocker, tmp_path):
    """Test push flow when branch already exists on remote."""
    repo_path = tmp_path / "repo"
    (repo_path / ".git").mkdir(parents=True)

    mocker.patch("os.chdir")

    mock_run = mocker.patch("src.publishers.tools.subprocess.run")
    mock_run.side_effect = [
        # git remote get-url origin
        subprocess.CompletedProcess(
            [], 0, stdout="https://github.com/test/repo.git\n", stderr=""
        ),
        # git fetch origin
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git branch --list main (exists locally)
        subprocess.CompletedProcess([], 0, stdout="  main\n", stderr=""),
        # git ls-remote --heads origin main (exists remotely)
        subprocess.CompletedProcess([], 0, stdout="abc\trefs/heads/main\n", stderr=""),
        # git rev-list --count origin/main..main
        subprocess.CompletedProcess([], 0, stdout="2\n", stderr=""),
        # git push origin main (no -u since branch exists)
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
    ]

    tools.github_push_branch(
        repository_url="https://github.com/test/repo.git",
        branch="main",
        repo_path=repo_path,
        remote="origin",
    )

    # Verify push command was called without -u for existing branch
    mock_run.assert_any_call(
        ["git", "push", "origin", "main"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_github_push_branch_force_push(mocker, tmp_path):
    """Test force push flag is passed correctly."""
    repo_path = tmp_path / "repo"
    (repo_path / ".git").mkdir(parents=True)

    mocker.patch("os.chdir")

    mock_run = mocker.patch("src.publishers.tools.subprocess.run")
    mock_run.side_effect = [
        # git remote get-url origin
        subprocess.CompletedProcess(
            [], 0, stdout="https://github.com/test/repo.git\n", stderr=""
        ),
        # git fetch origin
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        # git branch --list feature (exists locally)
        subprocess.CompletedProcess([], 0, stdout="  feature\n", stderr=""),
        # git ls-remote --heads origin feature (exists remotely)
        subprocess.CompletedProcess(
            [], 0, stdout="abc\trefs/heads/feature\n", stderr=""
        ),
        # git rev-list --count origin/feature..feature
        subprocess.CompletedProcess([], 0, stdout="1\n", stderr=""),
        # git push --force origin feature
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
    ]

    tools.github_push_branch(
        repository_url="https://github.com/test/repo.git",
        branch="feature",
        repo_path=repo_path,
        remote="origin",
        force=True,
    )

    # Verify push command was called with --force
    mock_run.assert_any_call(
        ["git", "push", "--force", "origin", "feature"],
        capture_output=True,
        text=True,
        check=True,
    )
