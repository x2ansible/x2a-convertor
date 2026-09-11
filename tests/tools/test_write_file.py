"""Tests for WriteFileTool."""

import pytest

from tools.write_file import WriteFileTool


@pytest.fixture
def tool():
    return WriteFileTool()


class TestWriteFileTool:
    def test_writes_file_contents(self, tool, tmp_path):
        file_path = tmp_path / "output.txt"

        result = tool._run(str(file_path), "hello world")

        assert "written successfully" in result
        assert file_path.read_text() == "hello world"

    def test_creates_missing_parent_directories(self, tool, tmp_path):
        file_path = tmp_path / "nested" / "deeper" / "output.txt"

        result = tool._run(str(file_path), "content")

        assert "written successfully" in result
        assert file_path.read_text() == "content"

    def test_overwrites_by_default(self, tool, tmp_path):
        file_path = tmp_path / "output.txt"
        file_path.write_text("original")

        tool._run(str(file_path), "replaced")

        assert file_path.read_text() == "replaced"

    def test_append_true_appends_to_existing_file(self, tool, tmp_path):
        file_path = tmp_path / "output.txt"
        file_path.write_text("first\n")

        tool._run(str(file_path), "second\n", append=True)

        assert file_path.read_text() == "first\nsecond\n"

    def test_append_true_creates_file_when_missing(self, tool, tmp_path):
        file_path = tmp_path / "output.txt"

        result = tool._run(str(file_path), "content", append=True)

        assert "written successfully" in result
        assert file_path.read_text() == "content"

    def test_returns_error_when_write_path_is_directory(self, tool, tmp_path):
        result = tool._run(str(tmp_path), "content")

        assert "Error" in result
