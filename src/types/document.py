"""Document file handling utilities"""

from dataclasses import dataclass
from pathlib import Path

__all__ = ["DocumentFile"]


@dataclass
class DocumentFile:
    path: Path
    content: str

    @classmethod
    def from_path(cls, file_path: str | Path) -> "DocumentFile":
        """Create DocumentFile from a file path by reading its content"""
        path_obj = Path(file_path)
        if not path_obj.exists():
            raise ValueError(f"File not found: '{file_path}'")
        content = path_obj.read_text()
        return cls(path=path_obj, content=content)

    def to_document(self) -> str:
        """Export as XML document format"""
        return f"""<document>
<source>{self.path}</source>
<document_content>
{self.content}
</document_content>
</document>"""
