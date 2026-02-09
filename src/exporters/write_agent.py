"""Write agent for Chef to Ansible migration.

Creates all migration files from the checklist.
"""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_core.tools import BaseTool
from langgraph.graph import START, StateGraph

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.exporters.agent_state import WriteAgentState
from src.exporters.state import ChefState
from src.model import get_runnable_config
from src.types import ChecklistStatus
from src.types.telemetry import AgentMetrics
from src.utils.config import get_config_int
from src.utils.logging import get_logger
from tools.ansible_lint import AnsibleLintTool
from tools.ansible_write import AnsibleWriteTool
from tools.copy_file import CopyFileWithMkdirTool
from tools.validated_write import ValidatedWriteTool

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class WriteAgent(BaseAgent[ChefState]):
    """Agent responsible for writing all migration files from checklist.

    This agent uses an internal StateGraph to manage file creation loops:
    - Attempts to write all files from checklist
    - Verifies file creation after each attempt
    - Retries until all files exist OR max attempts reached

    The agent returns only when complete or max attempts exhausted.
    """

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: FileSearchTool(),
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
        lambda: ValidatedWriteTool(),  # Auto-routes YAML to ansible_write
        lambda: CopyFileWithMkdirTool(),
        lambda: AnsibleWriteTool(),
        lambda: AnsibleLintTool(),
    ]

    SYSTEM_PROMPT_NAME = "export_ansible_write_system"
    USER_PROMPT_NAME = "export_ansible_write_task"

    def __init__(self, model=None, max_attempts=None):
        super().__init__(model)
        self.max_attempts = get_config_int("MAX_WRITE_ATTEMPTS")
        self._graph = self._build_internal_graph()
        self._current_metrics: AgentMetrics | None = None

    def extra_tools_from_state(self, state: ChefState) -> list[BaseTool]:
        if state.checklist is None:
            return []
        return state.checklist.get_tools()

    def _build_internal_graph(self):
        """Build the internal StateGraph for write workflow."""
        workflow = StateGraph(WriteAgentState)
        workflow.add_node("write_standard_files", self._write_standard_files_node)
        workflow.add_node("write_files", self._write_files_node)
        workflow.add_node("check_files", self._check_files_node)
        workflow.add_node("lint_files", self._lint_files_node)
        workflow.add_node("mark_failed", self._mark_failed_node)

        workflow.add_edge(START, "write_standard_files")
        workflow.add_edge("write_standard_files", "write_files")
        workflow.add_edge("write_files", "check_files")
        workflow.add_edge("check_files", "lint_files")
        workflow.add_conditional_edges("lint_files", self._evaluate_write_node)
        workflow.add_edge("mark_failed", "__end__")

        return workflow.compile()

    def _write_standard_files_node(self, state: WriteAgentState) -> WriteAgentState:
        """Node: Create standard boilerplate files before LLM agent runs."""
        chef_state = state.chef_state
        slog = logger.bind(phase="write_standard_files")
        slog.info("Creating standard boilerplate files")

        ansible_path = chef_state.get_ansible_path()
        meta_file_path = Path(ansible_path) / "meta" / "main.yml"

        role_name = chef_state.module
        meta_content = f"""---
galaxy_info:
  role_name: {role_name}
  author: Migration Tool
  description: Migrated from Chef to Ansible
  license: Apache-2.0
  min_ansible_version: "2.9"
  platforms:
    - name: Ubuntu
      versions:
        - bionic
        - focal
    - name: EL
      versions:
        - "7"
        - "8"
        - "9"
        - "10"
  galaxy_tags: []
"""

        meta_file_path.parent.mkdir(parents=True, exist_ok=True)
        meta_file_path.write_text(meta_content, encoding="utf-8")
        slog.info(f"Created: {meta_file_path}")

        target_path_str = str(meta_file_path)
        source_path = "N/A"

        assert chef_state.checklist is not None, (
            "Checklist must exist before writing files"
        )
        updated = chef_state.checklist.update_task(
            source_path=source_path,
            target_path=target_path_str,
            status=ChecklistStatus.COMPLETE,
            notes="Created standard meta/main.yml",
        )

        if not updated:
            chef_state.checklist.add_task(
                category="structure",
                source_path=source_path,
                target_path=target_path_str,
                status=ChecklistStatus.COMPLETE,
                description="Created standard meta/main.yml",
            )
            slog.info(f"Added task to checklist: {target_path_str}")

        chef_state.checklist.save(chef_state.get_checklist_path())
        state.chef_state = chef_state
        return state

    def _write_files_node(self, state: WriteAgentState) -> WriteAgentState:
        """Node: Write files from checklist using react agent."""
        chef_state = state.chef_state
        assert chef_state.checklist is not None, (
            "Checklist must exist before writing files"
        )
        slog = logger.bind(phase="write_files", attempt=state.attempt)
        slog.info("Writing migration files")

        slog.debug(f"Checklist before writing:\n{chef_state.checklist.to_markdown()}")

        ansible_path = chef_state.get_ansible_path()
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            module=chef_state.module,
            chef_path=chef_state.path,
            ansible_path=ansible_path,
            high_level_migration_plan=chef_state.high_level_migration_plan,
            migration_plan=chef_state.module_migration_plan.to_document(),
            checklist=chef_state.checklist.to_markdown()
            if chef_state.checklist
            else "",
            aap_discovery=chef_state.aap_discovery,
        )

        result = self.invoke_react(
            chef_state,
            [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt},
            ],
            self._current_metrics,
        )

        chef_state.checklist.save(chef_state.get_checklist_path())

        slog.info(f"Checklist after writing:\n{chef_state.checklist.to_markdown()}")
        message = self.get_last_ai_message(result)
        if message:
            chef_state = chef_state.update(last_output=message.content)
            slog.info("Write iteration completed")
        else:
            slog.warning("Write agent did not produce output")

        state.chef_state = chef_state
        state.last_result = result
        state.attempt += 1

        return state

    def _check_files_node(self, state: WriteAgentState) -> WriteAgentState:
        """Node: Check if all checklist files exist."""
        chef_state = state.chef_state
        assert chef_state.checklist is not None, (
            "Checklist must exist before checking files"
        )
        slog = logger.bind(phase="check_files", attempt=state.attempt)
        slog.info("Checking file creation status")

        missing_files = []
        for item in chef_state.checklist.items:
            if not item.target_exists():
                missing_files.append(item.target_path)
                chef_state.checklist.update_task(
                    item.source_path, item.target_path, ChecklistStatus.MISSING
                )

        chef_state.checklist.save(chef_state.get_checklist_path())

        if missing_files:
            slog.warning(f"Missing {len(missing_files)} files: {missing_files[:5]}...")
            state.missing_files = missing_files
            state.complete = False
        else:
            slog.info("All files created successfully!")
            state.missing_files = []
            state.complete = True

        chef_state = chef_state.update(
            write_attempt_counter=chef_state.write_attempt_counter + 1
        )
        state.chef_state = chef_state

        return state

    def _lint_files_node(self, state: WriteAgentState) -> WriteAgentState:
        """Node: Run ansible-lint with autofix on generated files."""
        chef_state = state.chef_state
        slog = logger.bind(phase="lint_files", attempt=state.attempt)

        if state.missing_files:
            slog.info("Skipping lint - files are missing")
            return state

        slog.info("Running ansible-lint with autofix on generated files")
        ansible_path = chef_state.get_ansible_path()
        lint_tool = AnsibleLintTool()

        try:
            result = lint_tool._run(ansible_path=ansible_path, autofix=True)
            slog.info(f"Ansible-lint result: {result}")
        except Exception as e:
            slog.error(f"Error running ansible-lint: {e}")

        return state

    def _mark_failed_node(self, state: WriteAgentState) -> WriteAgentState:
        """Node: Mark the migration as failed due to write errors."""
        slog = logger.bind(phase="mark_failed", attempt=state.attempt)
        slog.error(
            f"Max write attempts ({state.max_attempts}) reached, marking migration as failed"
        )

        assert state.missing_files is not None, (
            "missing_files must be set after file check"
        )
        missing_file_list = ", ".join(state.missing_files[:5])
        if len(state.missing_files) > 5:
            missing_file_list += f" ... and {len(state.missing_files) - 5} more"

        chef_state = state.chef_state.mark_failed(
            f"Failed to create {len(state.missing_files)} files after {state.max_attempts} attempts. "
            f"Missing files: {missing_file_list}"
        )
        state.chef_state = chef_state

        return state

    def _evaluate_write_node(
        self, state: WriteAgentState
    ) -> Literal["write_files", "mark_failed", "__end__"]:
        """Conditional edge: Decide whether to retry or finish."""
        slog = logger.bind(phase="evaluate_write", attempt=state.attempt)

        if state.complete:
            slog.info("Write agent complete - all files created")
            return "__end__"

        if state.attempt >= state.max_attempts:
            return "mark_failed"

        slog.info(
            f"Retrying write phase (attempt {state.attempt + 1}/{state.max_attempts})"
        )
        return "write_files"

    def execute(self, state: ChefState, metrics: AgentMetrics | None) -> ChefState:
        """Execute write workflow with internal retry loop."""
        from src.exporters.chef_to_ansible import MigrationPhase

        self._log.info("Starting write agent workflow")

        state = state.update(current_phase=MigrationPhase.WRITING)

        # Store metrics reference for internal nodes to use
        self._current_metrics = metrics

        # Early exit if all files already created
        assert state.checklist is not None, (
            "Checklist must exist before write agent execution"
        )
        if all(item.target_exists() for item in state.checklist.items):
            self._log.info("All files already created, skipping write agent")
            self._current_metrics = None
            return state

        internal_state = WriteAgentState(
            chef_state=state,
            attempt=0,
            max_attempts=self.max_attempts,
            complete=False,
        )

        final_state_dict = self._graph.invoke(internal_state, get_runnable_config())
        final_state = WriteAgentState(**final_state_dict)

        if metrics:
            metrics.record_metric("attempts", final_state.attempt)
            metrics.record_metric("complete", final_state.complete)
            if final_state.missing_files:
                metrics.record_metric("missing_files", len(final_state.missing_files))
            if final_state.chef_state.checklist:
                stats = final_state.chef_state.checklist.get_stats()
                metrics.record_metric("files_created", stats.get("complete", 0))
                metrics.record_metric("files_total", stats.get("total", 0))

        self._current_metrics = None

        self._log.info(
            f"Write agent finished: complete={final_state.complete}, "
            f"attempts={final_state.attempt}/{self.max_attempts}"
        )

        return final_state.chef_state
