"""Tests for the line-scoped ReadFileTool."""

import pytest

from tools.read_file import MAX_LINES_PER_READ, ReadFileTool


@pytest.fixture
def tool():
    return ReadFileTool()


class TestReadFileTool:
    def test_returns_error_for_missing_file(self, tool, tmp_path):
        result = tool._run(str(tmp_path / "nonexistent.txt"))
        assert "Error" in result

    def test_returns_error_for_directory(self, tool, tmp_path):
        result = tool._run(str(tmp_path))
        assert "Error" in result
        assert "not a file" in result

    def test_reads_full_small_file_by_default(self, tool, tmp_path):
        file_path = tmp_path / "small.txt"
        file_path.write_text("line1\nline2\nline3\n")
        result = tool._run(str(file_path))
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    def test_reads_lines_in_order(self, tool, tmp_path):
        file_path = tmp_path / "small.txt"
        file_path.write_text("alpha\nbeta\n")
        result = tool._run(str(file_path))
        lines = result.splitlines()
        assert lines[0] == "alpha"
        assert lines[1] == "beta"

    def test_start_line_and_end_line_scope_the_read(self, tool, tmp_path):
        file_path = tmp_path / "file.txt"
        file_path.write_text("\n".join(f"line{i}" for i in range(1, 11)))
        result = tool._run(str(file_path), start_line=3, end_line=5)
        assert "line3" in result
        assert "line4" in result
        assert "line5" in result
        assert "line2" not in result
        assert "line6" not in result

    def test_start_line_beyond_file_returns_error(self, tool, tmp_path):
        file_path = tmp_path / "file.txt"
        file_path.write_text("line1\nline2\n")
        result = tool._run(str(file_path), start_line=100)
        assert "Error" in result

    def test_caps_read_at_max_lines_per_call(self, tool, tmp_path):
        file_path = tmp_path / "big.txt"
        file_path.write_text(
            "\n".join(f"line{i}" for i in range(1, MAX_LINES_PER_READ + 50))
        )
        result = tool._run(str(file_path))
        body_lines = result.splitlines()
        assert len(body_lines) == MAX_LINES_PER_READ
        assert body_lines[0] == "line1"
        assert body_lines[-1] == f"line{MAX_LINES_PER_READ}"

    def test_end_line_beyond_file_is_clamped(self, tool, tmp_path):
        file_path = tmp_path / "small.txt"
        file_path.write_text("line1\nline2\nline3\n")
        result = tool._run(str(file_path), start_line=1, end_line=1000)
        assert "line1" in result
        assert "line3" in result
