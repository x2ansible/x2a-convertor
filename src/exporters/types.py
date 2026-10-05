"""Chef-to-Ansible exporter-specific types"""

from enum import StrEnum


class MoleculeStatus(StrEnum):
    """Generation and validation status of Molecule artifacts."""

    NOT_GENERATED = "not_generated"
    NOT_EXECUTED = "statically_validated_not_executed"
    GENERATION_FAILED = "generation_failed_unverified"


class MigrationCategory(StrEnum):
    """Categories of migration items"""

    TEMPLATES = "templates"
    RECIPES = "recipes"
    ATTRIBUTES = "attributes"
    FILES = "files"
    STRUCTURE = "structure"
    DEPENDENCIES = "dependencies"
    MOLECULE = "molecule"
    CREDENTIALS = "credentials"

    def to_title(self) -> str:
        """Return markdown title for this category"""
        titles = {
            self.TEMPLATES: "### Templates",
            self.RECIPES: "### Recipes → Tasks",
            self.ATTRIBUTES: "### Attributes → Variables",
            self.FILES: "### Static Files",
            self.STRUCTURE: "### Structure Files",
            self.DEPENDENCIES: "### Dependencies (requirements.yml)",
            self.MOLECULE: "### Molecule Testing",
            self.CREDENTIALS: "### Credentials → AAP Configuration",
        }
        return titles.get(self, f"### {self.value.title()}")
