"""Write missing deterministic Molecule scenario artifacts."""

from pathlib import Path


class MoleculeScenarioWriter:
    """Persist generated files without replacing existing user content."""

    def write_missing(self, files: dict[Path, str]) -> None:
        """Create parent directories and write only files that do not exist."""
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(content, encoding="utf-8")
