"""Chef-to-Ansible exporter-specific types"""

from enum import Enum


class MigrationCategory(str, Enum):
    """Categories of migration items"""

    TEMPLATES = "templates"
    RECIPES = "recipes"
    ATTRIBUTES = "attributes"
    FILES = "files"
    STRUCTURE = "structure"

    def to_title(self) -> str:
        """Return markdown title for this category"""
        titles = {
            self.TEMPLATES: "### Templates",
            self.RECIPES: "### Recipes → Tasks",
            self.ATTRIBUTES: "### Attributes → Variables",
            self.FILES: "### Static Files",
            self.STRUCTURE: "### Structure Files",
        }
        return titles.get(self, f"### {self.value.title()}")
