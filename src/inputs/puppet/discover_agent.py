"""Puppet control repo discovery agent.

Explores directory structure to discover control repo layout,
roles, profiles, and manifest files referencing the target module.
Replaces the procedural PuppetPathResolver with AI-powered discovery.
"""

from collections.abc import Callable
from typing import ClassVar

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_core.tools import BaseTool

from prompts.get_prompt import get_prompt
from src.inputs.input_agent import InputAgent
from src.inputs.puppet.models import PuppetDiscoveryResult
from src.inputs.puppet.state import PuppetState
from src.types.telemetry import AgentMetrics
from src.utils.path import Path
from tools.grep_file import GrepFileTool


class PuppetDiscoverAgent(InputAgent[PuppetState]):
    """Discover control repo structure and role/profile chain for a Puppet module.

    Two-phase approach:
    1. ReAct exploration -- navigate directories, read environment.conf,
       grep for module references in manifests
    2. Structured extraction -- parse discovery findings into PuppetDiscoveryResult
    """

    _NAME = "Puppet Control Repo Discovery"

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
        lambda: FileSearchTool(),
        lambda: GrepFileTool(),
    ]

    SYSTEM_PROMPT_NAME = "puppet_discover_system"
    TASK_PROMPT_NAME = "puppet_discover_task"

    def execute(self, state: PuppetState, metrics: AgentMetrics | None) -> PuppetState:
        discovery_content = self._discover(state, metrics)

        result = self._extract_discovery_result(discovery_content, metrics)
        if not result:
            self._log.info("No control repo context discovered -- standalone module")
            return state

        return self._apply_discovery(state, result)

    def _discover(self, state: PuppetState, metrics: AgentMetrics | None) -> str:
        """Run ReAct agent to explore directory structure and find references."""
        module_name = Path(state.path).resolve().name
        if Path(state.path).resolve().is_file():
            module_name = Path(state.path).resolve().parent.name

        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()

        task_prompt = get_prompt(self.TASK_PROMPT_NAME).format(
            path=state.path,
            module_name=module_name,
            dependencies_dir=state.dependencies_dir or "",
        )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": task_prompt},
        ]

        result = self.invoke_react(state, messages, metrics)
        ai_message = self.get_last_ai_message(result)
        if not ai_message:
            return ""
        return ai_message.text

    def _extract_discovery_result(
        self, discovery_content: str, metrics: AgentMetrics | None
    ) -> PuppetDiscoveryResult | None:
        """Extract structured discovery result from ReAct agent output."""
        if not discovery_content:
            return None

        messages = [
            {
                "role": "system",
                "content": (
                    "Extract the Puppet control repo discovery results "
                    "into a structured format. If no control repo was found "
                    "(no environment.conf), return null fields."
                ),
            },
            {"role": "user", "content": discovery_content},
        ]

        return self.invoke_structured(PuppetDiscoveryResult, messages, metrics)

    def _apply_discovery(
        self, state: PuppetState, result: PuppetDiscoveryResult
    ) -> PuppetState:
        """Map discovery result to state fields."""
        context_paths = [
            Path(p).relative_to_cwd()
            for p in result.context_manifest_paths
            if Path(p).exists()
        ]

        return state.update(
            control_repo_root=result.control_repo_root,
            context_manifest_paths=context_paths,
            role_class=result.role_class,
            profile_classes=result.profile_classes,
        )
