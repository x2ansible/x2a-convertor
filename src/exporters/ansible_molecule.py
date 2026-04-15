"""Molecule testing integration for Ansible roles

This module provides programmatic Molecule test execution for validating
generated Ansible roles. Uses Molecule's Python API directly.
"""

import io
import os
import signal
import uuid
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import structlog
from molecule.command import (
    converge,
    create,
    dependency,
    destroy,
    idempotence,
    syntax,
    verify,
)
from molecule.config import Config

logger = structlog.get_logger(__name__)


@contextmanager
def timeout(seconds: int):
    """Context manager for timeout on operations

    Args:
        seconds: Timeout duration in seconds

    Raises:
        TimeoutError: If operation exceeds timeout duration
    """

    def timeout_handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds} seconds")

    # Set alarm signal handler
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        # Restore previous handler and cancel alarm
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


@dataclass
class MoleculeTestResult:
    """Result of Molecule test execution"""

    success: bool
    phase_results: dict[str, bool]  # phase_name -> passed
    error_output: str
    full_output: str
    run_id: str  # UUID for this test run


class AnsibleMolecule:
    """Execute Molecule tests on Ansible roles

    Provides programmatic interface to run Molecule test suites with
    clean output parsing for AI agent consumption.
    """

    # Test phases: (name, command_class)
    TEST_PHASES: ClassVar = [
        ("dependency", dependency.Dependency),
        ("syntax", syntax.Syntax),
        ("create", create.Create),
        ("converge", converge.Converge),
        ("idempotence", idempotence.Idempotence),
        ("verify", verify.Verify),
    ]

    DEFAULT_PHASE_TIMEOUT = 600  # 10 minutes per phase

    def __init__(self, phase_timeout: int = 600):
        """Initialize Molecule test executor

        Args:
            phase_timeout: Timeout in seconds for each test phase (default: 600)
        """
        self.phase_timeout = phase_timeout

    def _get_molecule_file(
        self, role_path: Path, scenario_name: str = "default"
    ) -> Path:
        """Get path to Molecule configuration file

        Args:
            role_path: Path to the Ansible role directory
            scenario_name: Molecule scenario name (default: "default")

        Returns:
            Path to molecule.yml file
        """
        return role_path / "molecule" / scenario_name / "molecule.yml"

    def _check_dependencies(self) -> str | None:
        """Check if required dependencies are available

        Returns:
            Error message if dependencies missing, None if all present
        """
        # Delegated driver has no external dependencies
        return None

    def _setup_molecule_files(
        self, role_path: Path, role_name: str, force: bool = True
    ) -> None:
        """Generate Molecule configuration files dynamically

        Args:
            role_path: Path to the Ansible role directory
            role_name: Name of the role
            force: If True, regenerate files even if they exist (default: True)
        """
        molecule_dir = role_path / "molecule" / "default"
        molecule_dir.mkdir(parents=True, exist_ok=True)

        # Always regenerate if force=True to ensure clean state

        logger.info(f"Regenerating Molecule files for {role_name}")

        # Generate molecule.yml — delegated driver for AAP/OpenShift
        molecule_config = """---
driver:
  name: default

platforms:
  - name: molecule-test-instance
    groups:
      - all

provisioner:
  name: ansible
  env:
    ANSIBLE_ROLES_PATH: "${MOLECULE_PROJECT_DIRECTORY}/../"
  inventory:
    hosts:
      all:
        hosts:
          molecule-test-instance:
            ansible_connection: local

verifier:
  name: ansible
"""
        (molecule_dir / "molecule.yml").write_text(molecule_config)

        # Generate converge.yml — container-safe, no include_role, no become
        # All paths use /tmp/molecule_test/ prefix. WriteAgent generates the real one.
        converge_playbook = f"""---
- name: Converge
  hosts: all
  gather_facts: true
  tasks:
    - name: Placeholder — WriteAgent generates container-safe converge
      ansible.builtin.debug:
        msg: "Role {role_name} converge placeholder — use /tmp/molecule_test/ paths"
"""
        (molecule_dir / "converge.yml").write_text(converge_playbook)

        # Generate no-op create.yml and destroy.yml for delegated driver
        for playbook_name in ("create", "destroy"):
            noop_playbook = f"""---
- name: {playbook_name.capitalize()}
  hosts: localhost
  connection: local
  gather_facts: false
  tasks: []
"""
            (molecule_dir / f"{playbook_name}.yml").write_text(noop_playbook)

        # Generate verify.yml placeholder — WriteAgent generates the real one
        verify_playbook = f"""---
- name: Verify
  hosts: all
  gather_facts: true
  tasks:
    - name: Verify role {role_name} executed successfully
      ansible.builtin.debug:
        msg: "Role {role_name} applied successfully"
"""
        (molecule_dir / "verify.yml").write_text(verify_playbook)

        logger.info(f"Generated Molecule files in {molecule_dir}")

    def _execute_single_phase(
        self,
        phase_name: str,
        phase_class: type,
        molecule_file: Path,
        run_id: str,
        role_name: str,
        scenario_name: str,
    ) -> tuple[bool, str]:
        """Execute a single Molecule test phase

        Args:
            phase_name: Name of the test phase
            phase_class: Molecule command class for this phase
            molecule_file: Path to molecule.yml configuration
            run_id: UUID for this test run
            role_name: Name of the role being tested
            scenario_name: Molecule scenario name

        Returns:
            Tuple of (success, output_message)
        """
        log = logger.bind(
            run_id=run_id,
            role_name=role_name,
            scenario_name=scenario_name,
            phase_name=phase_name,
        )

        log.info("Starting Molecule phase", timeout_seconds=self.phase_timeout)

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        try:
            config = Config(
                molecule_file=str(molecule_file),
                command_args={"subcommand": phase_name},
            )

            cmd = phase_class(config)

            with (
                redirect_stdout(stdout_capture),
                redirect_stderr(stderr_capture),
                timeout(self.phase_timeout),
            ):
                cmd.execute()

            stdout_text = stdout_capture.getvalue()
            stderr_text = stderr_capture.getvalue()
            combined_output = stdout_text + stderr_text

            success_msg = f"Phase {phase_name} completed successfully\n\n"
            if combined_output.strip():
                success_msg += f"Output:\n```{combined_output}```"

            log.info(
                "Molecule phase completed successfully",
                output_lines=len(combined_output.splitlines()),
            )
            return (True, success_msg)

        except TimeoutError:
            stdout_text = stdout_capture.getvalue()
            stderr_text = stderr_capture.getvalue()
            combined_output = stdout_text + stderr_text

            error_msg = f"Phase {phase_name} timed out after {self.phase_timeout}s\n\n"
            if combined_output.strip():
                error_msg += f"Output before timeout:\n```{combined_output}```\n\n"

            log.error(
                "Molecule phase timed out",
                timeout_seconds=self.phase_timeout,
                output_lines=len(combined_output.splitlines()),
            )
            return (False, error_msg)

        except Exception as e:
            stdout_text = stdout_capture.getvalue()
            stderr_text = stderr_capture.getvalue()
            combined_output = stdout_text + stderr_text

            error_msg = f"Phase {phase_name} failed: {e!s}\n\n"
            if combined_output.strip():
                error_msg += f"Output:\n```{combined_output}```\n\n"
            error_msg += f"Exception: {type(e).__name__}: {e!s}"

            log.warning(
                "Molecule phase failed",
                error=str(e),
                exception_type=type(e).__name__,
                output_lines=len(combined_output.splitlines()),
            )
            return (False, error_msg)

    def _execute_test_phases(
        self,
        role_path: Path,
        role_name: str,
        run_id: str,
        scenario_name: str = "default",
    ) -> dict[str, tuple[bool, str]]:
        """Execute Molecule test phases using Python API

        Args:
            role_path: Path to the Ansible role directory
            role_name: Name of the role being tested
            run_id: UUID for this test run
            scenario_name: Molecule scenario name

        Returns:
            Dictionary mapping phase name to (success, output) tuple
        """
        results = {}
        molecule_file = self._get_molecule_file(role_path, scenario_name)

        if not molecule_file.exists():
            return {
                "config": (
                    False,
                    f"Molecule configuration not found: '{molecule_file}'",
                )
            }

        original_dir = Path.cwd()
        os.chdir(role_path)

        try:
            for phase_name, phase_class in self.TEST_PHASES:
                success, output = self._execute_single_phase(
                    phase_name,
                    phase_class,
                    molecule_file,
                    run_id,
                    role_name,
                    scenario_name,
                )
                results[phase_name] = (success, output)

                if not success:
                    break

        finally:
            os.chdir(original_dir)

        return results

    def _parse_results(
        self, phase_results: dict[str, tuple[bool, str]], run_id: str
    ) -> MoleculeTestResult:
        """Parse test results into structured format

        Args:
            phase_results: Dictionary of phase results
            run_id: UUID for this test run

        Returns:
            Structured test result
        """
        all_passed = all(passed for passed, _ in phase_results.values())
        phase_status = {phase: passed for phase, (passed, _) in phase_results.items()}

        # Collect error output from failed phases
        error_lines: list[str] = []
        full_lines: list[str] = []

        for phase, (passed, output) in phase_results.items():
            status_text = "PASSED" if passed else "FAILED"
            full_lines.append(f"=== Phase: {phase} ===")
            full_lines.append(f"Status: {status_text}")
            full_lines.append(output)
            full_lines.append("")

            if not passed:
                error_lines.append(f"Phase '{phase}' failed:")
                error_lines.append(output)
                error_lines.append("")

        return MoleculeTestResult(
            success=all_passed,
            phase_results=phase_status,
            error_output="\n".join(error_lines),
            full_output="\n".join(full_lines),
            run_id=run_id,
        )

    @classmethod
    def run(
        cls,
        role_path: str,
        phase_timeout: int = 600,
    ) -> MoleculeTestResult:
        """Run Molecule test suite on an Ansible role

        Args:
            role_path: Path to the Ansible role directory
            phase_timeout: Timeout in seconds for each test phase (default: 600)

        Returns:
            Test results with success status and detailed output
        """
        instance = cls(phase_timeout=phase_timeout)
        return instance._run(role_path)

    def _run(self, role_path: str) -> MoleculeTestResult:
        """Internal method to run Molecule test suite on an Ansible role

        Args:
            role_path: Path to the Ansible role directory

        Returns:
            Test results with success status and detailed output
        """
        role_path_obj = Path(role_path)
        role_name = role_path_obj.name
        run_id = str(uuid.uuid4())

        log = logger.bind(run_id=run_id, role_name=role_name)

        log.info(
            "Starting Molecule test run",
            role_path=str(role_path_obj),
            phase_timeout=self.phase_timeout,
        )

        # Validate path exists and is a directory
        if not role_path_obj.exists():
            error_msg = f"Role path does not exist: {role_path_obj}"
            log.error("Role path validation failed", error="path does not exist")
            return MoleculeTestResult(
                success=False,
                phase_results={},
                error_output=error_msg,
                full_output=error_msg,
                run_id=run_id,
            )

        if not role_path_obj.is_dir():
            error_msg = f"Role path is not a directory: {role_path_obj}"
            log.error("Role path validation failed", error="path is not a directory")
            return MoleculeTestResult(
                success=False,
                phase_results={},
                error_output=error_msg,
                full_output=error_msg,
                run_id=run_id,
            )

        # Check dependencies
        dep_error = self._check_dependencies()
        if dep_error:
            log.error("Dependency check failed", error=dep_error)
            return MoleculeTestResult(
                success=False,
                phase_results={},
                error_output=dep_error,
                full_output=dep_error,
                run_id=run_id,
            )

        # Destroy any existing instances first for clean state
        log.info("Cleaning up existing Molecule instances")
        self.cleanup(str(role_path_obj))

        # Always regenerate Molecule files for clean state
        log.info("Setting up Molecule configuration")
        self._setup_molecule_files(role_path_obj, role_name, force=True)

        # Execute test phases
        phase_results = self._execute_test_phases(role_path_obj, role_name, run_id)

        # Parse and return results
        result = self._parse_results(phase_results, run_id)

        if result.success:
            log.info(
                "Molecule test run PASSED",
                phases_passed=len([p for p, s in result.phase_results.items() if s]),
                total_phases=len(result.phase_results),
            )
        else:
            log.warning(
                "Molecule test run FAILED",
                phases_passed=len([p for p, s in result.phase_results.items() if s]),
                total_phases=len(result.phase_results),
            )

        return result

    @classmethod
    def cleanup(cls, role_path: str, scenario_name: str = "default") -> None:
        """Destroy Molecule test instances using Python API

        Args:
            role_path: Path to the Ansible role directory
            scenario_name: Molecule scenario name
        """
        instance = cls()
        role_path_obj = Path(role_path)
        molecule_file = instance._get_molecule_file(role_path_obj, scenario_name)

        if not molecule_file.exists():
            logger.warning(f"Molecule config not found: {molecule_file}")
            return

        original_dir = Path.cwd()
        os.chdir(role_path_obj)

        try:
            config = Config(
                molecule_file=str(molecule_file),
                command_args={"subcommand": "destroy"},
            )
            cmd = destroy.Destroy(config)
            cmd.execute()
            logger.info(f"Cleaned up Molecule instances for {role_path}")
        except Exception as e:
            logger.warning(f"Error cleaning up Molecule instances: {e}", exc_info=True)
        finally:
            os.chdir(original_dir)
