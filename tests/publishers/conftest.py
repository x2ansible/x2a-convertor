import pytest


@pytest.fixture
def sample_role_dir(tmp_path) -> str:
    """Create a sample role directory structure."""
    role_dir = tmp_path / "sample_role"
    (role_dir / "tasks").mkdir(parents=True)
    (role_dir / "meta").mkdir()
    (role_dir / "tasks" / "main.yml").write_text(
        "- name: Test task\n  debug:\n    msg: Hello"
    )
    (role_dir / "meta" / "main.yml").write_text("---\ndependencies: []")
    return str(role_dir)


@pytest.fixture
def sample_role_dir2(tmp_path) -> str:
    """Create a second sample role directory structure."""
    role_dir = tmp_path / "sample_role2"
    (role_dir / "tasks").mkdir(parents=True)
    (role_dir / "meta").mkdir()
    (role_dir / "tasks" / "main.yml").write_text(
        "- name: Test task 2\n  debug:\n    msg: World"
    )
    (role_dir / "meta" / "main.yml").write_text("---\ndependencies: []")
    return str(role_dir)
