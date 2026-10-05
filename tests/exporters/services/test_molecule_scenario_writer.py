from src.exporters.services.molecule_scenario_writer import MoleculeScenarioWriter


def test_writer_creates_parent_directories_for_missing_artifacts(tmp_path):
    generated = tmp_path / "nested" / "generated.yml"

    MoleculeScenarioWriter().write_missing({generated: "generated"})

    assert generated.read_text() == "generated"


def test_writer_preserves_existing_user_artifacts(tmp_path):
    existing = tmp_path / "existing.yml"
    existing.write_text("# user content\n")

    MoleculeScenarioWriter().write_missing({existing: "replacement"})

    assert existing.read_text() == "# user content\n"
