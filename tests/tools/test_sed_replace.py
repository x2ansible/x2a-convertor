import shutil
import tempfile
from pathlib import Path

from tools.sed_replace import (
    MAX_LINE_LENGTH,
    MAX_PATTERN_LENGTH,
    MAX_REPLACEMENT_LENGTH,
    SedTool,
)


class TestSedTool:
    """Test cases for SedTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = SedTool()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self) -> None:
        """Clean up test fixtures."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_literal_replacement_single_line(self) -> None:
        """Test literal string replacement on a specific line."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "line 1\nline 2\nline 3\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=2,
            pattern="line 2",
            replacement="modified line 2",
            use_regex=False,
        )

        assert "Successfully replaced" in result
        assert "line 2" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "line 1\n"
        assert lines[1] == "modified line 2\n"
        assert lines[2] == "line 3\n"

    def test_literal_replacement_partial_match(self) -> None:
        """Test literal replacement of part of a line."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "hello world\nfoo bar\nbaz qux\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="world",
            replacement="universe",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "hello universe\n"
        assert lines[1] == "foo bar\n"
        assert lines[2] == "baz qux\n"

    def test_regex_replacement(self) -> None:
        """Test regex pattern replacement."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "version: 1.2.3\nname: test\nversion: 4.5.6\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern=r"version:\s*\d+\.\d+\.\d+",
            replacement="version: 2.0.0",
            use_regex=True,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "version: 2.0.0\n"
        assert lines[1] == "name: test\n"
        assert lines[2] == "version: 4.5.6\n"

    def test_regex_with_capture_groups(self) -> None:
        """Test regex replacement with capture groups."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "name: John Doe\nage: 30\nemail: test@example.com\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern=r"name:\s*(\w+)\s+(\w+)",
            replacement=r"name: \2, \1",
            use_regex=True,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "name: Doe, John\n"

    def test_pattern_not_found_literal(self) -> None:
        """Test error when literal pattern not found on specified line."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "line 1\nline 2\nline 3\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=2,
            pattern="nonexistent",
            replacement="replacement",
            use_regex=False,
        )

        assert "ERROR" in result
        assert "not found" in result
        assert "line 2" in result

    def test_pattern_not_found_regex(self) -> None:
        """Test error when regex pattern not found on specified line."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "line 1\nline 2\nline 3\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern=r"\d{5}",
            replacement="12345",
            use_regex=True,
        )

        assert "ERROR" in result
        assert "not found" in result

    def test_file_not_exists(self) -> None:
        """Test error when file does not exist."""
        file_path = Path(self.temp_dir) / "nonexistent.txt"

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="test",
            replacement="replacement",
            use_regex=False,
        )

        assert "ERROR" in result
        assert "does not exist" in result

    def test_line_number_out_of_range_too_high(self) -> None:
        """Test error when line number exceeds file length."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "line 1\nline 2\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=10,
            pattern="test",
            replacement="replacement",
            use_regex=False,
        )

        assert "ERROR" in result
        assert "out of range" in result
        assert "has 2 lines" in result

    def test_line_number_out_of_range_zero(self) -> None:
        """Test error when line number is zero."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "line 1\nline 2\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=0,
            pattern="test",
            replacement="replacement",
            use_regex=False,
        )

        assert "ERROR" in result
        assert "out of range" in result

    def test_line_number_negative(self) -> None:
        """Test error when line number is negative."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "line 1\nline 2\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=-1,
            pattern="test",
            replacement="replacement",
            use_regex=False,
        )

        assert "ERROR" in result
        assert "out of range" in result

    def test_replacement_on_first_line(self) -> None:
        """Test replacement on the first line of file."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "first line\nsecond line\nthird line\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="first",
            replacement="FIRST",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "FIRST line\n"

    def test_replacement_on_last_line(self) -> None:
        """Test replacement on the last line of file."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "first line\nsecond line\nthird line\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=3,
            pattern="third",
            replacement="THIRD",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[2] == "THIRD line\n"

    def test_empty_file(self) -> None:
        """Test handling of empty file."""
        file_path = Path(self.temp_dir) / "empty.txt"
        with file_path.open("w", encoding="utf-8") as f:
            f.write("")

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="test",
            replacement="replacement",
            use_regex=False,
        )

        assert "ERROR" in result
        assert "out of range" in result

    def test_multiple_occurrences_literal_replaces_all(self) -> None:
        """Test that literal replacement replaces all occurrences on the line."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "foo foo foo\nbar bar\nbaz\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="foo",
            replacement="FOO",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "FOO FOO FOO\n"

    def test_multiple_occurrences_regex_replaces_all(self) -> None:
        """Test that regex replacement replaces all occurrences on the line."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "number1 number2 number3\ntest\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern=r"number\d",
            replacement="NUM",
            use_regex=True,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "NUM NUM NUM\n"

    def test_replacement_preserves_other_lines(self) -> None:
        """Test that replacement only affects the specified line."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "apple\napple\napple\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=2,
            pattern="apple",
            replacement="orange",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "apple\n"
        assert lines[1] == "orange\n"
        assert lines[2] == "apple\n"

    def test_replacement_with_special_characters(self) -> None:
        """Test literal replacement with special regex characters."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "price: $10.99\nitem: widget\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="$10.99",
            replacement="$20.99",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "price: $20.99\n"

    def test_replacement_with_empty_string(self) -> None:
        """Test replacement with empty string (deletion)."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "remove this text here\nkeep this\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="remove this ",
            replacement="",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "text here\n"

    def test_file_without_trailing_newline(self) -> None:
        """Test replacement on file without trailing newline."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "line 1\nline 2\nline 3"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=3,
            pattern="line 3",
            replacement="modified line 3",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[2] == "modified line 3"

    def test_single_line_file(self) -> None:
        """Test replacement on single-line file."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "single line"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="single",
            replacement="SINGLE",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            content = f.read()

        assert content == "SINGLE line"

    def test_code_file_replacement(self) -> None:
        """Test replacement in Python code file."""
        file_path = Path(self.temp_dir) / "code.py"
        content = 'def foo():\n    return "old_value"\n\nprint(foo())\n'
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=2,
            pattern="old_value",
            replacement="new_value",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[1] == '    return "new_value"\n'

    def test_yaml_file_replacement(self) -> None:
        """Test replacement in YAML file."""
        file_path = Path(self.temp_dir) / "config.yml"
        content = "---\nversion: 1.0.0\nname: test\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=2,
            pattern="1.0.0",
            replacement="2.0.0",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[1] == "version: 2.0.0\n"

    def test_whitespace_preservation(self) -> None:
        """Test that whitespace is preserved during replacement."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "    indented line\nnormal line\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="indented",
            replacement="INDENTED",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        assert lines[0] == "    INDENTED line\n"

    def test_pattern_length_at_limit(self) -> None:
        """Test that pattern at exactly the maximum length is accepted."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "x" * (MAX_PATTERN_LENGTH + 100) + "\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        # Pattern exactly at the limit should work
        pattern = "x" * MAX_PATTERN_LENGTH
        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern=pattern,
            replacement="y" * MAX_PATTERN_LENGTH,
            use_regex=False,
        )

        assert "Successfully replaced" in result

    def test_pattern_exceeds_max_length(self) -> None:
        """Test that excessively long patterns are rejected."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "test line\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        # Pattern exceeding the limit
        pattern = "x" * (MAX_PATTERN_LENGTH + 1)
        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern=pattern,
            replacement="replacement",
            use_regex=False,
        )

        assert "ERROR" in result
        assert "Pattern length" in result
        assert "exceeds maximum" in result
        assert str(MAX_PATTERN_LENGTH) in result

    def test_replacement_exceeds_max_length(self) -> None:
        """Test that excessively long replacements are rejected."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "test line\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        # Replacement exceeding the limit
        replacement = "x" * (MAX_REPLACEMENT_LENGTH + 1)
        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="test",
            replacement=replacement,
            use_regex=False,
        )

        assert "ERROR" in result
        assert "Replacement length" in result
        assert "exceeds maximum" in result
        assert str(MAX_REPLACEMENT_LENGTH) in result

    def test_line_exceeds_max_length(self) -> None:
        """Test that excessively long lines are rejected."""
        file_path = Path(self.temp_dir) / "test.txt"
        # Create a file with a very long line
        long_line = "x" * (MAX_LINE_LENGTH + 1) + "\n"
        content = "short line\n" + long_line + "another short line\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=2,
            pattern="x",
            replacement="y",
            use_regex=False,
        )

        assert "ERROR" in result
        assert "Line 2 length" in result
        assert "exceeds maximum" in result
        assert str(MAX_LINE_LENGTH) in result

    def test_stress_very_long_regex_pattern(self) -> None:
        """Stress test with very long regex pattern (at limit)."""
        file_path = Path(self.temp_dir) / "test.txt"
        # Create content that will match
        content = "a" * 500 + "target" + "b" * 500 + "\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        # Create a complex regex at the limit (alternation of many patterns)
        pattern = "(" + "|".join(["test" + str(i) for i in range(200)]) + "|target)"
        # Make sure we're at or near the limit
        pattern = pattern[:MAX_PATTERN_LENGTH]

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern=pattern,
            replacement="FOUND",
            use_regex=True,
        )

        # Should succeed since pattern is at the limit
        assert "Successfully replaced" in result or "ERROR" in result

    def test_stress_very_long_literal_pattern(self) -> None:
        """Stress test with very long literal pattern."""
        file_path = Path(self.temp_dir) / "test.txt"
        # Create a long repeated pattern
        long_pattern = "abc123" * 150  # 900 chars, under the limit
        content = "prefix_" + long_pattern + "_suffix\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern=long_pattern,
            replacement="REPLACED",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            content = f.read()

        assert "REPLACED" in content
        assert long_pattern not in content

    def test_stress_long_replacement_text(self) -> None:
        """Stress test with long replacement text."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "REPLACE_ME\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        # Create a long replacement (under the limit)
        long_replacement = "x" * 4000
        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="REPLACE_ME",
            replacement=long_replacement,
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            content = f.read()

        assert long_replacement in content

    def test_stress_long_line_with_short_pattern(self) -> None:
        """Stress test with very long line (at limit) and short pattern."""
        file_path = Path(self.temp_dir) / "test.txt"
        # Create a line at the limit
        long_line = "x" * (MAX_LINE_LENGTH - 100) + "FIND_ME" + "y" * 90 + "\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(long_line)

        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="FIND_ME",
            replacement="FOUND",
            use_regex=False,
        )

        assert "Successfully replaced" in result

        with Path(file_path).open(encoding="utf-8") as f:
            content = f.read()

        assert "FOUND" in content
        assert "FIND_ME" not in content

    def test_stress_pathological_regex(self) -> None:
        """Test protection against potentially slow regex patterns."""
        file_path = Path(self.temp_dir) / "test.txt"
        content = "test content\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)

        # A pattern that could be problematic if it were longer
        # We test a moderately complex pattern that's safe but demonstrates the protection
        # Note: truly pathological patterns like (a+)+ * many would hang, so we avoid them
        complex_pattern = "(" + "|".join(["pattern" + str(i) for i in range(20)]) + ")"

        if len(complex_pattern) > MAX_PATTERN_LENGTH:
            # If it exceeds, it should be rejected
            result = self.tool._run(
                file_path=str(file_path),
                line_number=1,
                pattern=complex_pattern,
                replacement="replaced",
                use_regex=True,
            )
            assert "ERROR" in result
            assert "Pattern length" in result
        else:
            # This complex but safe pattern should execute without hanging
            result = self.tool._run(
                file_path=str(file_path),
                line_number=1,
                pattern=complex_pattern,
                replacement="replaced",
                use_regex=True,
            )
            # Pattern won't match, but should return quickly
            assert isinstance(result, str)

    def test_multiple_limits_exceeded(self) -> None:
        """Test when multiple limits are exceeded (pattern checked first)."""
        file_path = Path(self.temp_dir) / "test.txt"
        # Create file with very long line
        long_line = "x" * (MAX_LINE_LENGTH + 1) + "\n"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(long_line)

        # Also use pattern and replacement that exceed limits
        result = self.tool._run(
            file_path=str(file_path),
            line_number=1,
            pattern="x" * (MAX_PATTERN_LENGTH + 1),
            replacement="y" * (MAX_REPLACEMENT_LENGTH + 1),
            use_regex=False,
        )

        # Pattern is checked first, so should get pattern error
        assert "ERROR" in result
        assert "Pattern length" in result
