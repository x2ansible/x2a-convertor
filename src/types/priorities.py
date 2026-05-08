"""Priorities generation types for init workflow."""

from pathlib import Path

from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)

SECTION_SEPARATOR = "\n\n---\n\n"


class PrioritiesSection(BaseModel):
    """A single thematic block within a priorities file.

    Represents one section of rules/guidelines relevant to a specific
    migration phase (input analysis or export).
    """

    title: str = Field(description="Section title describing the rule theme")
    content: str = Field(description="Section content with the relevant rules")

    def to_markdown(self) -> str:
        """Render this section as markdown."""
        return f"## {self.title}\n\n{self.content}"


class PrioritiesOutput(BaseModel):
    """Structured output for priorities generation.

    Contains two lists of sections: one for input/analysis agents
    and one for export/write agents.
    """

    input_priorities: list[PrioritiesSection] = Field(
        description="Priorities for input/analysis agents (technology-specific rules)"
    )
    export_priorities: list[PrioritiesSection] = Field(
        description="Priorities for export/write agents (Ansible output rules)"
    )

    def write_input_file(self, filename: str) -> None:
        """Write input priorities to a file.

        Args:
            filename: Output file path (e.g., INPUT-AGENTS.md)
        """
        _write_sections_file(filename, self.input_priorities)

    def write_export_file(self, filename: str) -> None:
        """Write export priorities to a file.

        Args:
            filename: Output file path (e.g., EXPORT-AGENTS.md)
        """
        _write_sections_file(filename, self.export_priorities)


def _write_sections_file(filename: str, sections: list[PrioritiesSection]) -> None:
    """Write a list of sections to a markdown file.

    Sections are joined with '---' separators. If sections list is empty,
    the file is not written.

    Args:
        filename: Output file path
        sections: List of PrioritiesSection to write
    """
    if not sections:
        logger.debug(f"No sections for {filename}, skipping file creation")
        return

    content = SECTION_SEPARATOR.join(section.to_markdown() for section in sections)
    Path(filename).write_text(content, encoding="utf-8")
    logger.info(f"Priorities file created: {filename} ({len(sections)} sections)")
