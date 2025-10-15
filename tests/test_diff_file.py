import os
import tempfile
import pytest
from tools.diff_file import DiffFileTool


class TestDiffFileTool:
    @pytest.fixture
    def tool(self) -> DiffFileTool:
        return DiffFileTool()

    def test_diff_shows_differences(self, tool) -> None:
        source_content = "line 1\nline 2\nline 3\n"
        dest_content = "line 1\nmodified line 2\nline 3\n"

        with (
            tempfile.NamedTemporaryFile(mode="w", delete=False) as source,
            tempfile.NamedTemporaryFile(mode="w", delete=False) as dest,
        ):
            source.write(source_content)
            dest.write(dest_content)
            source_path = source.name
            dest_path = dest.name

        try:
            result = tool._run(source_path, dest_path)
            assert "No differences found" not in result
            assert "line 2" in result
            assert "modified line 2" in result
        finally:
            os.unlink(source_path)
            os.unlink(dest_path)

    def test_diff_with_identical_files(self, tool) -> None:
        content = "test content\nline 2\n"

        with (
            tempfile.NamedTemporaryFile(mode="w", delete=False) as f1,
            tempfile.NamedTemporaryFile(mode="w", delete=False) as f2,
        ):
            f1.write(content)
            f2.write(content)
            f1_path = f1.name
            f2_path = f2.name

        try:
            result = tool._run(f1_path, f2_path)
            assert "No differences found" in result
        finally:
            os.unlink(f1_path)
            os.unlink(f2_path)

    def test_source_file_not_found(self, tool) -> None:
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as dest:
            dest_path = dest.name

        try:
            result = tool._run("/nonexistent/source.txt", dest_path)
            assert "Error: Source file not found" in result
        finally:
            os.unlink(dest_path)

    def test_destination_file_not_found(self, tool) -> None:
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as source:
            source_path = source.name

        try:
            result = tool._run(source_path, "/nonexistent/dest.txt")
            assert "Error: Destination file not found" in result
        finally:
            os.unlink(source_path)
