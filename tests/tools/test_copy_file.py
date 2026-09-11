"""Tests for CopyFileWithMkdirTool."""

import pytest

from tools.copy_file import CopyFileWithMkdirTool


@pytest.fixture
def tool():
    return CopyFileWithMkdirTool()


class TestCopyFileWithMkdirTool:
    def test_copies_file_contents(self, tool, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("hello world")
        destination = tmp_path / "destination.txt"

        result = tool._run(str(source), str(destination))

        assert "copied successfully" in result
        assert destination.read_text() == "hello world"

    def test_creates_missing_parent_directories(self, tool, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("content")
        destination = tmp_path / "nested" / "deeper" / "destination.txt"

        result = tool._run(str(source), str(destination))

        assert "copied successfully" in result
        assert destination.exists()
        assert destination.read_text() == "content"

    def test_returns_error_for_missing_source(self, tool, tmp_path):
        source = tmp_path / "missing.txt"
        destination = tmp_path / "destination.txt"

        result = tool._run(str(source), str(destination))

        assert "Error" in result
        assert not destination.exists()

    def test_does_not_follow_symlinks(self, tool, tmp_path):
        real_target = tmp_path / "real.txt"
        real_target.write_text("real content")
        symlink_source = tmp_path / "link.txt"
        symlink_source.symlink_to(real_target)
        destination = tmp_path / "destination.txt"

        result = tool._run(str(symlink_source), str(destination))

        assert "copied successfully" in result
        assert destination.is_symlink()
        assert destination.readlink() == real_target

    def test_preserves_file_metadata(self, tool, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("content")
        source.chmod(0o644)
        destination = tmp_path / "destination.txt"

        tool._run(str(source), str(destination))

        assert oct(destination.stat().st_mode)[-3:] == "644"
