"""Tests for GrepFileTool content search."""

import pytest

from tools.grep_file import MAX_GREP_RESULTS, GrepFileTool


@pytest.fixture
def tool():
    return GrepFileTool()


@pytest.fixture
def search_dir(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "main.yml").write_text(
        "- name: restart nginx\n  shell: systemctl restart nginx\n- name: copy config\n  copy:\n    src: nginx.conf\n"
    )
    (tmp_path / "tasks" / "install.yml").write_text(
        "- name: install nginx\n  ansible.builtin.package:\n    name: nginx\n    state: present\n"
    )
    (tmp_path / "vars").mkdir()
    (tmp_path / "vars" / "main.yml").write_text(
        "nginx_port: 80\nnginx_user: www-data\n"
    )
    (tmp_path / "README.md").write_text("# Nginx role\nInstalls nginx.\n")
    return tmp_path


class TestGrepFileTool:
    def test_finds_match_in_single_file(self, tool, search_dir):
        result = tool._run("systemctl", path=str(search_dir))
        assert "systemctl" in result

    def test_returns_no_matches_when_pattern_absent(self, tool, search_dir):
        result = tool._run("NONEXISTENT_PATTERN_XYZ", path=str(search_dir))
        assert result == "No matches found"

    def test_returns_error_for_missing_path(self, tool, tmp_path):
        result = tool._run("pattern", path=str(tmp_path / "nonexistent"))
        assert "Error" in result

    def test_returns_error_for_invalid_regex(self, tool, search_dir):
        result = tool._run("[unclosed", path=str(search_dir))
        assert "Error" in result
        assert "invalid regex" in result

    def test_result_format_includes_file_and_line_number(self, tool, search_dir):
        result = tool._run("nginx_port", path=str(search_dir))
        assert "nginx_port" in result
        parts = result.split(":")
        assert len(parts) >= 3

    def test_matches_across_multiple_files(self, tool, search_dir):
        result = tool._run("nginx", path=str(search_dir))
        lines = result.splitlines()
        files = {line.split(":")[0] for line in lines if line}
        assert len(files) > 1

    def test_regex_pattern_works(self, tool, search_dir):
        result = tool._run(r"nginx_\w+", path=str(search_dir))
        assert "nginx_port" in result or "nginx_user" in result

    def test_case_sensitive_by_default(self, tool, search_dir):
        result_lower = tool._run("nginx", path=str(search_dir))
        result_upper = tool._run("NGINX", path=str(search_dir))
        assert result_lower != "No matches found"
        assert result_upper == "No matches found"

    def test_search_single_file(self, tool, search_dir):
        file_path = str(search_dir / "vars" / "main.yml")
        result = tool._run("nginx_port", path=file_path)
        assert "nginx_port" in result
        assert "nginx_user" not in result

    def test_include_filter_limits_to_matching_files(self, tool, search_dir):
        result = tool._run("nginx", path=str(search_dir), include="*.md")
        lines = [
            line for line in result.splitlines() if line and line != "No matches found"
        ]
        assert all("README" in line for line in lines)

    def test_include_filter_yml_excludes_md(self, tool, search_dir):
        result = tool._run("nginx", path=str(search_dir), include="*.yml")
        assert "README" not in result

    def test_include_filter_with_no_matching_files(self, tool, search_dir):
        result = tool._run("nginx", path=str(search_dir), include="*.rb")
        assert result == "No matches found"

    def test_grep_finds_matches(self, tool, search_dir):
        results = tool._grep("shell", search_dir, include=None)
        assert len(results) > 0

    def test_grep_returns_line_numbers(self, tool, search_dir):
        results = tool._grep("shell", search_dir, include=None)
        for matches in results.values():
            for line_num, _ in matches:
                assert isinstance(line_num, int)
                assert line_num >= 1

    def test_grep_include_filter(self, tool, search_dir):
        results = tool._grep("nginx", search_dir, include="*.md")
        file_names = [str(k) for k in results]
        assert all("README" in f for f in file_names)

    def test_grep_no_match_returns_empty(self, tool, search_dir):
        results = tool._grep("ZZZNOMATCH", search_dir, include=None)
        assert results == {}

    def test_grep_regex_pattern(self, tool, search_dir):
        results = tool._grep(r"nginx_\w+:", search_dir, include=None)
        assert len(results) > 0

    def test_truncates_at_max_results(self, tool, tmp_path):
        content = "\n".join(f"match line {i}" for i in range(MAX_GREP_RESULTS + 10))
        (tmp_path / "big.txt").write_text(content)
        result = tool._run("match", path=str(tmp_path))
        content_lines = [
            line for line in result.splitlines() if not line.startswith("...")
        ]
        assert len(content_lines) == MAX_GREP_RESULTS

    def test_truncation_message_present_when_limit_exceeded(self, tool, tmp_path):
        content = "\n".join(f"match line {i}" for i in range(MAX_GREP_RESULTS + 10))
        (tmp_path / "big.txt").write_text(content)
        result = tool._run("match", path=str(tmp_path))
        assert "truncated" in result
        assert str(MAX_GREP_RESULTS) in result

    def test_no_truncation_when_under_limit(self, tool, tmp_path):
        content = "\n".join(f"match line {i}" for i in range(MAX_GREP_RESULTS - 1))
        (tmp_path / "small.txt").write_text(content)
        result = tool._run("match", path=str(tmp_path))
        assert "truncated" not in result
        assert len(result.splitlines()) == MAX_GREP_RESULTS - 1

    def test_truncation_at_exact_limit(self, tool, tmp_path):
        content = "\n".join(f"match line {i}" for i in range(MAX_GREP_RESULTS))
        (tmp_path / "exact.txt").write_text(content)
        result = tool._run("match", path=str(tmp_path))
        assert "truncated" not in result
        assert len(result.splitlines()) == MAX_GREP_RESULTS
