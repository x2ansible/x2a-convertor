"""Write agent for Chef to Ansible migration.

Creates all migration files from the checklist.
"""

from pathlib import Path
from typing import Literal, TYPE_CHECKING

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langgraph.graph import StateGraph, START, END

from src.exporters.agent_state import WriteAgentState
from src.exporters.base_agent import BaseAgent
from src.exporters.state import ChefState
from src.model import (
    get_last_ai_message,
    get_runnable_config,
    report_tool_calls,
)
from src.types import ChecklistStatus
from src.utils.config import get_config_int
from src.utils.logging import get_logger
from prompts.get_prompt import get_prompt

# from tools.ansible_lint import AnsibleLintTool
from tools.ansible_write import AnsibleWriteTool
from tools.copy_file import CopyFileWithMkdirTool
from tools.validated_write import ValidatedWriteTool

if TYPE_CHECKING:
    from src.exporters.chef_to_ansible import MigrationPhase

logger = get_logger(__name__)


class WriteAgent(BaseAgent):
    """Agent responsible for writing all migration files from checklist.

    This agent uses an internal StateGraph to manage file creation loops:
    - Attempts to write all files from checklist
    - Verifies file creation after each attempt
    - Retries until all files exist OR max attempts reached

    The agent returns only when complete or max attempts exhausted.
    """

    # Base tools that this agent always has access to
    BASE_TOOLS = [
        lambda: FileSearchTool(),
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
        lambda: ValidatedWriteTool(),  # Auto-routes YAML to ansible_write
        lambda: CopyFileWithMkdirTool(),
        lambda: AnsibleWriteTool(),
        # lambda: AnsibleLintTool(),
    ]

    SYSTEM_PROMPT_NAME = "export_ansible_write_system"
    USER_PROMPT_NAME = "export_ansible_write_task"

    def __init__(self, model=None, max_attempts=10):
        """Initialize write agent with optional model and max attempts.

        Args:
            model: LLM model to use (defaults to get_model())
            max_attempts: Maximum write attempts (defaults to MAX_WRITE_ATTEMPTS config)
        """
        super().__init__(model)
        self.max_attempts = max_attempts or get_config_int("MAX_WRITE_ATTEMPTS")
        self._graph = self._build_internal_graph()

    def _build_internal_graph(self):
        """Build the internal StateGraph for write workflow.

        Graph structure:
        START → write_standard_files → write_files → check_files → evaluate → END
                                                                        ↓
                                                                  (loop back if incomplete)
        """
        workflow = StateGraph(WriteAgentState)
        workflow.add_node("write_standard_files", self._write_standard_files_node)
        workflow.add_node("write_files", self._write_files_node)
        workflow.add_node("check_files", self._check_files_node)

        workflow.add_edge(START, "write_standard_files")
        workflow.add_edge("write_standard_files", "write_files")
        workflow.add_edge("write_files", "check_files")
        workflow.add_conditional_edges("check_files", self._evaluate_write_node)

        return workflow.compile()

    def _write_standard_files_node(self, state: WriteAgentState) -> WriteAgentState:
        """Node: Create standard boilerplate files before LLM agent runs.

        Creates simple files like meta/main.yml with known-good templates,
        then updates the checklist to mark them as complete.

        Args:
            state: Internal agent state

        Returns:
            Updated agent state with files created and checklist updated
        """
        chef_state = state.chef_state
        slog = logger.bind(phase="write_standard_files")
        slog.info("Creating standard boilerplate files")

        # 1. CREATE meta/main.yml directly
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
  galaxy_tags: []
"""

        meta_file_path.parent.mkdir(parents=True, exist_ok=True)
        meta_file_path.write_text(meta_content, encoding="utf-8")
        slog.info(f"Created: {meta_file_path}")

        target_path_str = str(meta_file_path)
        source_path = "N/A"  # No direct source file for meta/main.yml

        assert chef_state.checklist is not None, (
            "Checklist must exist before writing files"
        )
        # Try to update existing task
        updated = chef_state.checklist.update_task(
            source_path=source_path,
            target_path=target_path_str,
            status=ChecklistStatus.COMPLETE,
            notes="Created standard meta/main.yml",
        )

        # If task doesn't exist, add it
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
        """Node: Write files from checklist using react agent.

        Args:
            state: Internal agent state

        Returns:
            Updated agent state with last_result
        """
        chef_state = state.chef_state
        assert chef_state.checklist is not None, (
            "Checklist must exist before writing files"
        )
        slog = logger.bind(phase="write_files", attempt=state.attempt)
        slog.info("Writing migration files")

        slog.debug(f"Checklist before writing:\n{chef_state.checklist.to_markdown()}")

        agent = self._create_react_agent(chef_state)

        ansible_path = chef_state.get_ansible_path()
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            module=chef_state.module,
            chef_path=chef_state.path,
            ansible_path=ansible_path,
            high_level_migration_plan=chef_state.high_level_migration_plan.to_document(),
            migration_plan=chef_state.module_migration_plan.to_document(),
            checklist=chef_state.checklist.to_markdown()
            if chef_state.checklist
            else "",
        )

        result = agent.invoke(
            input={
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            },
            config=get_runnable_config(),
        )

        slog.info(f"Write agent tools: {report_tool_calls(result).to_string()}")
        chef_state.checklist.save(chef_state.get_checklist_path())

        slog.info(f"Checklist after writing:\n{chef_state.checklist.to_markdown()}")
        message = get_last_ai_message(result)
        if message:
            chef_state = chef_state.update(last_output=message.content)
            slog.info("Write iteration completed")
        else:
            slog.warning("Write agent did not produce output")

        # Update internal state
        state.chef_state = chef_state
        state.last_result = result
        state.attempt += 1

        return state

    def _check_files_node(self, state: WriteAgentState) -> WriteAgentState:
        """Node: Check if all checklist files exist.

        Args:
            state: Internal agent state

        Returns:
            Updated agent state with missing_files and complete flag
        """
        chef_state = state.chef_state
        assert chef_state.checklist is not None, (
            "Checklist must exist before checking files"
        )
        slog = logger.bind(phase="check_files", attempt=state.attempt)
        slog.info("Checking file creation status")

        # Check file existence for all checklist items
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

        # Update chef_state with incremented counter
        chef_state = chef_state.update(
            write_attempt_counter=chef_state.write_attempt_counter + 1
        )
        state.chef_state = chef_state

        return state

    def _evaluate_write_node(
        self, state: WriteAgentState
    ) -> Literal["write_files", "__end__"]:
        """Conditional edge: Decide whether to retry or finish.

        Args:
            state: Internal agent state

        Returns:
            Next node name or END
        """
        slog = logger.bind(phase="evaluate_write", attempt=state.attempt)

        if state.complete:
            slog.info("Write agent complete - all files created")
            return "__end__"

        if state.attempt >= state.max_attempts:
            slog.error(
                f"Max write attempts ({state.max_attempts}) reached, marking migration as failed"
            )
            # Mark migration as failed
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
            return "__end__"

        slog.info(
            f"Retrying write phase (attempt {state.attempt + 1}/{state.max_attempts})"
        )
        return "write_files"

    def __call__(self, state: ChefState) -> ChefState:
        """Execute write workflow with internal retry loop.

        Args:
            state: Current migration state

        Returns:
            Updated ChefState after all write attempts
        """
        from src.exporters.chef_to_ansible import MigrationPhase

        slog = logger.bind(phase="write_migration")
        slog.info("Starting write agent workflow")

        # Set current phase
        state = state.update(current_phase=MigrationPhase.WRITING)

        # Early exit if all files already created
        assert state.checklist is not None, (
            "Checklist must exist before write agent execution"
        )
        if all(item.target_exists() for item in state.checklist.items):
            slog.info("All files already created, skipping write agent")
            return state

        # Create internal state and run internal graph
        internal_state = WriteAgentState(
            chef_state=state,
            attempt=0,
            max_attempts=self.max_attempts,
            complete=False,
        )

        final_state_dict = self._graph.invoke(internal_state, get_runnable_config())

        # Convert dict back to WriteAgentState
        final_state = WriteAgentState(**final_state_dict)

        slog.info(
            f"Write agent finished: complete={final_state.complete}, "
            f"attempts={final_state.attempt}/{self.max_attempts}"
        )

        return final_state.chef_state
