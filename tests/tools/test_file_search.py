"""Tests for FileSearchTool."""

import pytest

from tools.file_search import FileSearchTool


@pytest.fixture
def tool():
    return FileSearchTool()


class TestFileSearchTool:
    def test_finds_matching_files_in_dir(self, tool, tmp_path):
        (tmp_path / "a.yml").write_text("")
        (tmp_path / "b.yml").write_text("")
        (tmp_path / "c.txt").write_text("")

        result = tool._run(pattern="*.yml", dir_path=str(tmp_path))

        assert "a.yml" in result
        assert "b.yml" in result
        assert "c.txt" not in result

    def test_finds_matching_files_recursively(self, tool, tmp_path):
        nested = tmp_path / "nested" / "deeper"
        nested.mkdir(parents=True)
        (nested / "target.yml").write_text("")

        result = tool._run(pattern="*.yml", dir_path=str(tmp_path))

        relative_path = str((nested / "target.yml").relative_to(tmp_path))
        assert relative_path in result

    def test_returns_no_files_found_message_when_no_matches(self, tool, tmp_path):
        (tmp_path / "a.txt").write_text("")

        result = tool._run(pattern="*.yml", dir_path=str(tmp_path))

        assert "No files found" in result

    def test_defaults_to_current_directory(self, tool, tmp_path, monkeypatch):
        (tmp_path / "target.yml").write_text("")
        monkeypatch.chdir(tmp_path)

        result = tool._run(pattern="*.yml")

        assert "target.yml" in result

    def test_returns_error_for_missing_directory(self, tool, tmp_path):
        result = tool._run(pattern="*.yml", dir_path=str(tmp_path / "missing"))

        assert "No files found" in result or "Error" in result
