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
        filename: Relative path of the rule file (e.g., "init/discovery.md")
        content: Full text content of the rule file
    """

    filename: str
    content: str

    @classmethod
    def from_path(cls, file_path: Path, base_dir: Path | None = None) -> "RuleFile":
        """Create RuleFile by reading a file from disk.

        Args:
            file_path: Path to the markdown rule file
            base_dir: Base directory for computing relative filename.
                      If provided, filename is relative to this directory.
                      Otherwise, only the file's basename is used.

        Returns:
            RuleFile with filename and content populated
        """
        filename = str(file_path.relative_to(base_dir)) if base_dir else file_path.name
        return cls(
            filename=filename,
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
        """Recursively load all markdown files from a directory.

        Args:
            directory: Path to the rules directory

        Returns:
            RuleCollection with rules sorted by relative path.
            Empty collection if directory is missing or has no .md files.
        """
        rules_path = Path(directory)
        if not rules_path.is_dir():
            return cls(rules=[])

        md_files = sorted(rules_path.rglob("*.md"))
        return cls(rules=[RuleFile.from_path(f, base_dir=rules_path) for f in md_files])

    def is_empty(self) -> bool:
        """Check if the collection has no rules."""
        return len(self.rules) == 0

    @property
    def total_chars(self) -> int:
        """Total character count across all rule contents."""
        return sum(len(rule.content) for rule in self.rules)

    def to_document(self) -> str:
        """Export all rules as XML document block for LLM context."""
        if self.is_empty():
            return ""

        rule_docs = "\n".join(rule.to_document() for rule in self.rules)
        return f"<organizational_rules>\n{rule_docs}\n</organizational_rules>"
