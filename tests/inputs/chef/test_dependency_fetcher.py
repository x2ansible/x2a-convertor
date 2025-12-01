"""Integration tests for ChefDependencyManager factory."""

import json
from pathlib import Path

import pytest

from src.inputs.chef.dependency_fetcher import ChefDependencyManager


class TestChefDependencyManagerFactory:
    """Test ChefDependencyManager factory and strategy detection."""

    def test_detect_policyfile_cookbook(self, tmp_path):
        """Test detection of Policyfile-based cookbook."""
        (tmp_path / "Policyfile.lock.json").write_text('{"name": "test"}')

        manager = ChefDependencyManager(str(tmp_path))
        assert manager._strategy.__class__.__name__ == "PolicyDependencyStrategy"

    def test_detect_berkshelf_cookbook(self, tmp_path):
        """Test detection of Berkshelf-based cookbook."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        manager = ChefDependencyManager(str(tmp_path))
        assert manager._strategy.__class__.__name__ == "BerksDependencyStrategy"

    def test_policyfile_takes_priority_over_berks(self, tmp_path):
        """Test that Policyfile has higher priority than Berks."""
        # Create both
        (tmp_path / "Policyfile.lock.json").write_text('{"name": "test"}')
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        manager = ChefDependencyManager(str(tmp_path))
        # Should choose Policy strategy
        assert manager._strategy.__class__.__name__ == "PolicyDependencyStrategy"

    def test_no_valid_cookbook_raises_error(self, tmp_path):
        """Test that invalid cookbook raises RuntimeError."""
        with pytest.raises(
            RuntimeError, match="No compatible Chef dependency strategy"
        ):
            ChefDependencyManager(str(tmp_path))

    def test_error_message_shows_expected_files(self, tmp_path):
        """Test that error message lists expected files."""
        with pytest.raises(RuntimeError) as exc_info:
            ChefDependencyManager(str(tmp_path))

        error_msg = str(exc_info.value)
        assert "Policyfile.lock.json" in error_msg
        assert "Berksfile" in error_msg
        assert "metadata.rb" in error_msg


class TestChefDependencyManagerBackwardCompatibility:
    """Test backward compatibility of ChefDependencyManager API."""

    def test_cookbook_path_property(self, tmp_path):
        """Test cookbook_path property."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        manager = ChefDependencyManager(str(tmp_path))
        assert manager.cookbook_path == tmp_path

    def test_export_dir_property(self, tmp_path):
        """Test export_dir property."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        manager = ChefDependencyManager(str(tmp_path))
        assert manager.export_dir is None

    def test_export_path_property_alias(self, tmp_path):
        """Test export_path property (backward compatibility alias)."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        manager = ChefDependencyManager(str(tmp_path))
        # export_path should be an alias for export_dir
        assert manager.export_path == manager.export_dir

    def test_has_dependencies_with_berks(self, tmp_path):
        """Test has_dependencies method with Berks strategy."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        manager = ChefDependencyManager(str(tmp_path))
        has_deps, _deps = manager.has_dependencies()

        # Without berks installed, should return False
        # (In real environment with berks, this would parse berks list output)
        assert has_deps is False

    def test_has_dependencies_no_deps(self, tmp_path):
        """Test has_dependencies when no dependencies exist."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        manager = ChefDependencyManager(str(tmp_path))
        has_deps, deps = manager.has_dependencies()

        assert has_deps is False
        assert len(deps) == 0

    def test_get_dependencies_paths_method(self, tmp_path):
        """Test get_dependencies_paths method (with 's')."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        manager = ChefDependencyManager(str(tmp_path))
        # Should have this method for backward compatibility
        paths = manager.get_dependencies_paths([])
        assert paths == []

    def test_get_dependency_paths_method(self, tmp_path):
        """Test get_dependency_paths method (without 's')."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        manager = ChefDependencyManager(str(tmp_path))
        # Should have this method too
        paths = manager.get_dependency_paths([])
        assert paths == []

    def test_context_manager_support(self, tmp_path):
        """Test context manager support."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")
        (tmp_path / "metadata.json").write_text(
            json.dumps({"name": "test", "version": "1.0.0", "dependencies": {}})
        )

        with ChefDependencyManager(str(tmp_path)) as manager:
            assert manager is not None
            # Simulate having export dir
            manager._strategy._export_dir = Path("test-cleanup")
            manager._strategy._export_dir.mkdir(exist_ok=True)

        # Should be cleaned up
        assert not Path("test-cleanup").exists()

    def test_cleanup_method(self, tmp_path):
        """Test cleanup method."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")
        (tmp_path / "metadata.json").write_text(
            json.dumps({"name": "test", "version": "1.0.0", "dependencies": {}})
        )

        manager = ChefDependencyManager(str(tmp_path))

        # Create test export dir
        test_dir = Path("test-cleanup-method")
        test_dir.mkdir(exist_ok=True)
        manager._strategy._export_dir = test_dir

        # Cleanup should remove it
        manager.cleanup()
        assert not test_dir.exists()
        assert manager._strategy._export_dir is None
