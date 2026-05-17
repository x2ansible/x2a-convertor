"""Tests for MigrationAgent — text fallback and extract_text_content."""

from src.exporters.migrate import MigrationAgent, SourceMetadata


class TestExtractTextContent:
    def test_string_input(self):
        assert MigrationAgent._extract_text_content('{"path": "."}') == '{"path": "."}'

    def test_list_with_text_block(self):
        content = [
            {"type": "reasoning_content", "reasoning_content": {"text": "thinking..."}},
            {"type": "text", "text": '{"path": "profile_haproxy"}'},
        ]
        assert (
            MigrationAgent._extract_text_content(content)
            == '{"path": "profile_haproxy"}'
        )

    def test_list_with_string_element(self):
        content = ['{"path": "."}']
        assert MigrationAgent._extract_text_content(content) == '{"path": "."}'

    def test_list_without_text_block(self):
        content = [
            {"type": "reasoning_content", "reasoning_content": {"text": "thinking..."}},
        ]
        assert MigrationAgent._extract_text_content(content) is None

    def test_none_input(self):
        assert MigrationAgent._extract_text_content(None) is None

    def test_empty_list(self):
        assert MigrationAgent._extract_text_content([]) is None

    def test_integer_input(self):
        assert MigrationAgent._extract_text_content(42) is None

    def test_list_prefers_text_type_over_string(self):
        content = [
            {"type": "text", "text": "first"},
            "second",
        ]
        assert MigrationAgent._extract_text_content(content) == "first"


class TestSourceMetadata:
    def test_from_valid_json(self):
        m = SourceMetadata(path=".")
        assert m.path == "."

    def test_from_module_path(self):
        m = SourceMetadata(path="profile_haproxy")
        assert m.path == "profile_haproxy"
