from tools.yaml_tools import YamlValidateTool, YamlLintTool


class TestYamlValidateTool:
    """Test cases for YamlValidateTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = YamlValidateTool()

    def test_valid_yaml(self) -> None:
        """Test validation of valid YAML content."""
        yaml_content = """
name: test
version: 1.0
items:
  - item1
  - item2
"""
        result = self.tool._run(yaml_content)
        assert "name: test" in result
        assert "version: 1.0" in result
        assert "Error" not in result

    def test_valid_yaml_with_nested_structure(self) -> None:
        """Test validation of complex nested YAML."""
        yaml_content = """
database:
  host: localhost
  port: 5432
  credentials:
    username: admin
    password: secret
"""
        result = self.tool._run(yaml_content)
        assert "database:" in result
        assert "credentials:" in result
        assert "Error" not in result

    def test_invalid_yaml_syntax(self) -> None:
        """Test validation of invalid YAML syntax."""
        yaml_content = """
name: test
  invalid: indentation
    more: problems
"""
        result = self.tool._run(yaml_content)
        assert "error" in result.lower()

    def test_malformed_yaml(self) -> None:
        """Test validation of malformed YAML."""
        yaml_content = """
key: [unclosed bracket
another: value
"""
        result = self.tool._run(yaml_content)
        assert "error" in result.lower()

    def test_empty_yaml(self) -> None:
        """Test validation of empty YAML."""
        yaml_content = ""
        result = self.tool._run(yaml_content)
        assert "Error" in result or "null" in result.lower()

    def test_yaml_with_special_characters(self) -> None:
        """Test validation of YAML with special characters."""
        yaml_content = """
message: "Hello, World!"
path: /usr/bin/test
regex: "^[a-z]+$"
"""
        result = self.tool._run(yaml_content)
        assert "message:" in result
        assert "Error" not in result

    def test_yaml_formatting(self) -> None:
        """Test that tool returns properly formatted YAML."""
        yaml_content = "name:    test\nversion:  1.0"
        result = self.tool._run(yaml_content)
        assert result.strip().startswith("name:")
        assert "version:" in result


class TestYamlLintTool:
    """Test cases for YamlLintTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = YamlLintTool()

    def test_valid_yaml(self) -> None:
        """Test linting of valid YAML content."""
        yaml_content = """
name: test
version: 1.0
items:
  - item1
  - item2
"""
        result = self.tool._run(yaml_content)
        assert result == "Valid YAML"

    def test_valid_yaml_complex(self) -> None:
        """Test linting of complex valid YAML."""
        yaml_content = """
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    environment:
      - DEBUG=true
"""
        result = self.tool._run(yaml_content)
        assert result == "Valid YAML"

    def test_invalid_yaml_syntax(self) -> None:
        """Test linting of invalid YAML syntax."""
        yaml_content = """
name: test
  invalid: indentation
"""
        result = self.tool._run(yaml_content)
        assert "error" in result.lower()
        assert "Valid YAML" not in result

    def test_yaml_syntax_error_with_location(self) -> None:
        """Test that syntax errors include location information."""
        yaml_content = """
valid: yaml
bad: [unclosed
"""
        result = self.tool._run(yaml_content)
        assert "error" in result.lower()

    def test_empty_yaml(self) -> None:
        """Test linting of empty YAML."""
        yaml_content = ""
        result = self.tool._run(yaml_content)
        assert "Warning" in result or "null" in result.lower()

    def test_yaml_with_tabs(self) -> None:
        """Test linting of YAML with tab characters."""
        yaml_content = "name: test\n\tvalue: something"
        result = self.tool._run(yaml_content)
        assert "error" in result.lower()

    def test_multiple_documents(self) -> None:
        """Test linting of YAML with multiple documents."""
        yaml_content = """---
doc1: value1
---
doc2: value2
"""
        result = self.tool._run(yaml_content)
        assert "Valid YAML" in result or "error" in result.lower()
