"""Rule file handling utilities.

Provides structured access to organizational rule files from the rules/ directory,
following the DocumentFile pattern for consistent document representation.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RuleFile:
    """A single organizational rule file.

    Attributes:
        filename: Name of the rule file (e.g., "discovery.md")
        content: Full text content of the rule file
    """

    filename: str
    content: str

    @classmethod
    def from_path(cls, file_path: Path) -> "RuleFile":
        """Create RuleFile by reading a file from disk.

        Args:
            file_path: Path to the markdown rule file

        Returns:
            RuleFile with filename and content populated
        """
        return cls(
            filename=file_path.name,
            content=file_path.read_text(encoding="utf-8"),
        )

    def to_document(self) -> str:
        """Export as XML document format for LLM context."""
        return f'<rule file="{self.filename}">\n{self.content}\n</rule>'


@dataclass
class RuleCollection:
    """Collection of organizational rule files.

    Attributes:
        rules: List of RuleFile instances, sorted alphabetically by filename
    """

    rules: list[RuleFile]

    @classmethod
    def from_directory(cls, directory: str | Path) -> "RuleCollection":
        """Load all markdown files from a directory.

        Args:
            directory: Path to the rules directory

        Returns:
            RuleCollection with rules sorted by filename.
            Empty collection if directory is missing or has no .md files.
        """
        rules_path = Path(directory)
        if not rules_path.is_dir():
            return cls(rules=[])

        md_files = sorted(rules_path.glob("*.md"))
        return cls(rules=[RuleFile.from_path(f) for f in md_files])

    def is_empty(self) -> bool:
        """Check if the collection has no rules."""
        return len(self.rules) == 0

    def to_document(self) -> str:
        """Export all rules as XML document block for LLM context."""
        if self.is_empty():
            return ""

        rule_docs = "\n".join(rule.to_document() for rule in self.rules)
        return f"<organizational_rules>\n{rule_docs}\n</organizational_rules>"
