"""Rules generation types for init workflow."""

from pathlib import Path

from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)

SECTION_SEPARATOR = "\n\n---\n\n"


class RuleSection(BaseModel):
    """A single thematic block within a rules file.

    Represents one section of rules/guidelines relevant to a specific
    migration phase (input analysis or export).
    """

    title: str = Field(description="Section title describing the rule theme")
    content: str = Field(description="Section content with the relevant rules")

    def to_markdown(self) -> str:
        """Render this section as markdown."""
        return f"## {self.title}\n\n{self.content}"


class RulesOutput(BaseModel):
    """Structured output for rules generation.

    Contains two lists of sections: one for input/analysis agents
    and one for export/write agents.
    """

    input_rules: list[RuleSection] = Field(
        description="Rules for input/analysis agents (technology-specific rules)"
    )
    export_rules: list[RuleSection] = Field(
        description="Rules for export/write agents (Ansible output rules)"
    )

    def write_input_file(self, filename: str) -> None:
        """Write input rules to a file.

        Args:
            filename: Output file path (e.g., INPUT-AGENTS.md)
        """
        _write_sections_file(filename, self.input_rules)

    def write_export_file(self, filename: str) -> None:
        """Write export rules to a file.

        Args:
            filename: Output file path (e.g., EXPORT-AGENTS.md)
        """
        _write_sections_file(filename, self.export_rules)


def _write_sections_file(filename: str, sections: list[RuleSection]) -> None:
    """Write a list of sections to a markdown file.

    Sections are joined with '---' separators. If sections list is empty,
    the file is not written.

    Args:
        filename: Output file path
        sections: List of RuleSection to write
    """
    if not sections:
        logger.debug(f"No sections for {filename}, skipping file creation")
        return

    content = SECTION_SEPARATOR.join(section.to_markdown() for section in sections)
    Path(filename).write_text(content, encoding="utf-8")
    logger.info(f"Rules file created: {filename} ({len(sections)} sections)")
