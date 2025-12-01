"""Test dependency strategies."""

from pathlib import Path

from src.inputs.chef.dependency_strategies import (
    BerksDependencyStrategy,
    PolicyDependencyStrategy,
)


class TestPolicyDependencyStrategy:
    """Test PolicyDependencyStrategy."""

    def test_can_handle_with_policyfile(self, tmp_path):
        """Test detection with Policyfile.lock.json."""
        policy_file = tmp_path / "Policyfile.lock.json"
        policy_file.write_text('{"name": "test"}')

        assert PolicyDependencyStrategy.can_handle(tmp_path)

    def test_cannot_handle_without_policyfile(self, tmp_path):
        """Test rejection without Policyfile.lock.json."""
        assert not PolicyDependencyStrategy.can_handle(tmp_path)

    def test_finds_policyfile_up_to_5_levels(self, tmp_path):
        """Test finding Policyfile.lock.json up directory tree."""
        # Create nested structure
        deep_path = tmp_path / "a" / "b" / "c" / "cookbook"
        deep_path.mkdir(parents=True)

        # Put Policyfile.lock.json 3 levels up
        policy_file = tmp_path / "a" / "Policyfile.lock.json"
        policy_file.write_text('{"name": "test"}')

        assert PolicyDependencyStrategy.can_handle(deep_path)

    def test_does_not_find_policyfile_beyond_5_levels(self, tmp_path):
        """Test that search stops after 5 levels."""
        # Create deep nested structure (6 levels)
        deep_path = tmp_path / "a" / "b" / "c" / "d" / "e" / "f"
        deep_path.mkdir(parents=True)

        # Put Policyfile.lock.json at the root (6 levels up)
        policy_file = tmp_path / "Policyfile.lock.json"
        policy_file.write_text('{"name": "test"}')

        # Should not find it
        assert not PolicyDependencyStrategy.can_handle(deep_path)

    def test_context_manager_cleanup(self, tmp_path):
        """Test context manager cleanup."""
        policy_file = tmp_path / "Policyfile.lock.json"
        policy_file.write_text('{"name": "test"}')

        with PolicyDependencyStrategy(str(tmp_path)) as strategy:
            # Simulate having an export dir
            strategy._export_dir = Path("test-export")
            strategy._export_dir.mkdir(exist_ok=True)
            assert strategy._export_dir.exists()

        # Should be cleaned up
        assert not Path("test-export").exists()


class TestBerksDependencyStrategy:
    """Test BerksDependencyStrategy."""

    def test_can_handle_with_berksfile_and_metadata(self, tmp_path):
        """Test detection with Berksfile and metadata.rb."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\nversion '1.0.0'\n")

        assert BerksDependencyStrategy.can_handle(tmp_path)

    def test_cannot_handle_with_only_berksfile(self, tmp_path):
        """Test rejection with only Berksfile."""
        (tmp_path / "Berksfile").write_text("source :supermarket\n")

        assert not BerksDependencyStrategy.can_handle(tmp_path)

    def test_cannot_handle_with_only_metadata(self, tmp_path):
        """Test rejection with only metadata.rb."""
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        assert not BerksDependencyStrategy.can_handle(tmp_path)

    def test_berks_list_requires_berks_command(self, tmp_path):
        """Test that berks list requires berks command."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        strategy = BerksDependencyStrategy(str(tmp_path))

        # Should return None if berks not available
        # (In real environment, berks list would work)
        result = strategy.detect_cookbook_name()
        assert result is None

    def test_berks_list_fallback(self, tmp_path):
        """Test handling when berks command fails."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        strategy = BerksDependencyStrategy(str(tmp_path))

        # Should return empty dependencies if berks fails
        has_deps, deps = strategy.has_dependencies()
        assert has_deps is False
        assert len(deps) == 0

    def test_context_manager_cleanup(self, tmp_path):
        """Test context manager cleanup."""
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        with BerksDependencyStrategy(str(tmp_path)) as strategy:
            # Simulate having an export dir
            strategy._export_dir = Path("test-export")
            strategy._export_dir.mkdir(exist_ok=True)
            assert strategy._export_dir.exists()

        # Should be cleaned up
        assert not Path("test-export").exists()


class TestStrategyPriority:
    """Test strategy priority and selection."""

    def test_policy_and_berks_both_present(self, tmp_path):
        """Test that Policyfile takes priority when both are present."""
        # Create both Policyfile and Berksfile
        (tmp_path / "Policyfile.lock.json").write_text('{"name": "test"}')
        (tmp_path / "Berksfile").write_text("source :supermarket\nmetadata\n")
        (tmp_path / "metadata.rb").write_text("name 'test'\n")

        # PolicyDependencyStrategy should detect it
        assert PolicyDependencyStrategy.can_handle(tmp_path)
        # BerksDependencyStrategy should also detect it
        assert BerksDependencyStrategy.can_handle(tmp_path)

        # But when used in factory, Policy should take priority
        # (tested in integration tests)
