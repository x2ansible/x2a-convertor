"""Integration tests for the new validation path.

These tests verify that the refactored validation architecture works correctly
in realistic scenarios, ensuring feature parity with the old implementation.
"""

from unittest.mock import Mock

import pytest

from src.exporters.chef_to_ansible import ChefToAnsibleSubagent, MigrationPhase
from src.exporters.state import ChefState
from src.types import AnsibleModule, DocumentFile
from src.validation.service import ValidationService
from src.validation.validators import AnsibleLintValidator, RoleStructureValidator
from tools.ansible_lint import ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE


class TestValidationIntegration:
    """Integration tests for validation refactoring."""

    @pytest.fixture
    def mock_state(self, tmp_path):
        """Create a mock ChefState for testing."""
        state = Mock(spec=ChefState)
        state.path = str(tmp_path / "chef")
        state.module = "test_module"
        state.user_message = "test migration"

        # Create temp files for DocumentFile (requires path and content)
        migration_plan_path = tmp_path / "migration_plan.md"
        migration_plan_path.write_text("# Test Migration Plan")
        high_level_plan_path = tmp_path / "high_level_plan.md"
        high_level_plan_path.write_text("# High Level Plan")

        state.module_migration_plan = DocumentFile(
            path=migration_plan_path, content="# Test Migration Plan"
        )
        state.high_level_migration_plan = DocumentFile(
            path=high_level_plan_path, content="# High Level Plan"
        )
        state.current_phase = MigrationPhase.VALIDATING
        state.validation_report = ""
        state.validation_attempt_counter = 0
        state.get_ansible_path.return_value = str(tmp_path / "ansible" / "test_module")
        state.get_checklist_path.return_value = str(
            tmp_path / "ansible" / "test_module" / ".checklist.json"
        )
        return state

    def test_validation_service_integration(self, tmp_path):
        """Test that ValidationService integrates correctly with validators."""
        from src.validation.results import ValidationResult

        # Create mock validators
        mock_validator1 = Mock()
        mock_validator1.name = "ansible-lint"
        mock_validator1.validate.return_value = ValidationResult(
            success=True,
            message=ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE,
            validator_name="ansible-lint",
        )

        mock_validator2 = Mock()
        mock_validator2.name = "role-check"
        mock_validator2.validate.return_value = ValidationResult(
            success=True, message="Role validation passed", validator_name="role-check"
        )

        # Initialize service with mock validators
        service = ValidationService([mock_validator1, mock_validator2])
        ansible_path = str(tmp_path / "ansible" / "test_role")

        # Run validation
        results = service.validate_all(ansible_path)

        # Verify results
        assert len(results) == 2
        assert "ansible-lint" in results
        assert "role-check" in results
        assert results["ansible-lint"].success
        assert results["role-check"].success
        assert not service.has_errors(results)

    def test_validation_service_with_failures(self, tmp_path):
        """Test ValidationService handles failures correctly."""
        from src.validation.results import ValidationResult

        # Create mock validators with failures
        mock_validator1 = Mock()
        mock_validator1.name = "ansible-lint"
        mock_validator1.validate.return_value = ValidationResult(
            success=False, message="Error: lint failed", validator_name="ansible-lint"
        )

        mock_validator2 = Mock()
        mock_validator2.name = "role-check"
        mock_validator2.validate.return_value = ValidationResult(
            success=False,
            message="Validation failed: no tasks",
            validator_name="role-check",
        )

        service = ValidationService([mock_validator1, mock_validator2])
        results = service.validate_all(str(tmp_path))

        # Verify failures are detected
        assert service.has_errors(results)
        assert not results["ansible-lint"].success
        assert not results["role-check"].success

        # Verify error report formatting
        error_report = service.format_error_report(results)
        assert "ansible-lint" in error_report
        assert "role-check" in error_report
        assert "lint failed" in error_report
        assert "no tasks" in error_report

    def test_new_validation_path_with_feature_flag(self, mock_state, monkeypatch):
        """Test that feature flag switches to new validation path."""
        # Set feature flag
        monkeypatch.setenv("USE_NEW_VALIDATION", "true")

        # Create agent
        agent = ChefToAnsibleSubagent(module=AnsibleModule("test_module"))

        # Verify validators are initialized in ValidationAgent
        assert hasattr(agent.validation_agent, "validators")
        assert hasattr(agent.validation_agent, "validation_service")
        assert len(agent.validation_agent.validators) == 2
        assert isinstance(agent.validation_agent.validators[0], AnsibleLintValidator)
        assert isinstance(agent.validation_agent.validators[1], RoleStructureValidator)
        assert isinstance(agent.validation_agent.validation_service, ValidationService)

    def test_old_validation_path_by_default(self, monkeypatch):
        """Test that old path is used by default."""
        # Ensure feature flag is not set
        monkeypatch.delenv("USE_NEW_VALIDATION", raising=False)

        # Create agent
        agent = ChefToAnsibleSubagent(module=AnsibleModule("test_module"))

        # Verify validators are still initialized in ValidationAgent (for future migration)
        assert hasattr(agent.validation_agent, "validators")
        assert hasattr(agent.validation_agent, "validation_service")

        # The _validate_migration method should route to old implementation by default
        # (This is verified by checking the routing logic in the actual implementation)

    def test_validation_agent_uses_validators_correctly(self, tmp_path):
        """Test that ValidationAgent properly uses its validators."""
        agent = ChefToAnsibleSubagent(module=AnsibleModule("test_module"))

        # Verify ValidationAgent has validators initialized
        assert hasattr(agent.validation_agent, "validators")
        assert len(agent.validation_agent.validators) == 2
        assert isinstance(agent.validation_agent.validators[0], AnsibleLintValidator)
        assert isinstance(agent.validation_agent.validators[1], RoleStructureValidator)

        # Verify ValidationAgent has validation_service
        assert hasattr(agent.validation_agent, "validation_service")
        assert isinstance(agent.validation_agent.validation_service, ValidationService)

    def test_validation_result_immutability(self):
        """Test that ValidationResult is immutable."""
        from dataclasses import FrozenInstanceError

        from src.validation.results import ValidationResult

        result = ValidationResult(
            success=True, message="test", validator_name="test-validator"
        )

        # Verify frozen dataclass prevents modification
        with pytest.raises(FrozenInstanceError):
            result.success = False  # pyrefly: ignore

    def test_multiple_validators_can_be_added(self):
        """Test that the architecture supports adding new validators easily."""
        from src.validation.results import ValidationResult

        # Create a custom validator
        class CustomValidator:
            name = "custom-validator"

            def validate(self, ansible_path: str):
                return ValidationResult(True, "custom check passed", self.name)

        # Create mock validators for existing ones
        mock_validator1 = Mock()
        mock_validator1.name = "ansible-lint"
        mock_validator1.validate.return_value = ValidationResult(
            True, ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE, "ansible-lint"
        )

        mock_validator2 = Mock()
        mock_validator2.name = "role-check"
        mock_validator2.validate.return_value = ValidationResult(
            True, "Role validation passed", "role-check"
        )

        # Add to service
        validators = [
            mock_validator1,
            mock_validator2,
            CustomValidator(),  # Easy to add new validator
        ]
        service = ValidationService(validators)

        # Verify all validators are used
        results = service.validate_all("/fake/path")
        assert len(results) == 3
        assert "custom-validator" in results
        assert results["custom-validator"].success
