"""Compose the Molecule scenario templates, writer, and static validator."""

from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.exporters.services.molecule_scenario_templates import MoleculeScenarioTemplates
from src.exporters.services.molecule_scenario_validator import MoleculeScenarioValidator
from src.exporters.services.molecule_scenario_writer import MoleculeScenarioWriter


class MoleculeProject:
    """Coordinate independent deterministic generation and validation services."""

    def __init__(
        self,
        layout: AnsibleProjectLayout,
        templates: MoleculeScenarioTemplates | None = None,
        writer: MoleculeScenarioWriter | None = None,
        validator: MoleculeScenarioValidator | None = None,
    ) -> None:
        self.layout = layout
        self.templates = templates or MoleculeScenarioTemplates(layout)
        self.writer = writer or MoleculeScenarioWriter()
        self.validator = validator or MoleculeScenarioValidator(layout)

    def scaffold(self) -> None:
        """Render and write deterministic files without replacing user edits."""
        self.writer.write_missing(self.templates.files())

    def validate_scaffold(self) -> list[str]:
        """Report infrastructure errors that verification generation cannot repair."""
        return self.validator.validate(
            self.templates.files(), include_verification=False
        )

    def validate(self) -> list[str]:
        """Validate generated YAML and the LLM-owned verification playbook."""
        paths = [*self.templates.files(), self.layout.molecule_verify_path]
        return self.validator.validate(paths)
