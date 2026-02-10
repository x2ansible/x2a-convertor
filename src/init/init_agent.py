"""Init agent orchestrator using LangGraph StateGraph.

This module contains the InitAgent class that orchestrates the init workflow
following the same pattern as the exporters (ChefToAnsibleSubagent).
"""

from pathlib import Path
from typing import Literal

from langgraph.graph import END, START, StateGraph

from src.const import METADATA_FILENAME, MIGRATION_PLAN_FILE
from src.init.init_state import InitState
from src.init.initialize_subagent import InitializeSubAgent
from src.init.metadata_extraction_agent import MetadataExtractionAgent
from src.model import get_model, get_runnable_config
from src.utils.logging import get_logger

logger = get_logger(__name__)


class InitAgent:
    """Agent orchestrating the init workflow using LangGraph StateGraph.

    Workflow:
    1. check_refresh: Determine if we can skip plan generation
    2. generate_plan: Run ReAct agent to create migration-plan.md (conditional)
    3. extract_metadata: Use structured output to generate `generated-project-metadata.json`
    4. finalize: Save state and report results

    The workflow uses conditional edges to skip plan generation when in refresh mode
    and the plan already exists.
    """

    def __init__(self, model=None):
        slog = logger.bind(phase="init_agent")
        self.model = model or get_model()
        self.initialize_agent = InitializeSubAgent(model=self.model)
        self.metadata_agent = MetadataExtractionAgent(model=self.model)
        self._workflow = self._create_workflow()
        slog.debug(self._workflow.get_graph().draw_mermaid())

    def _create_workflow(self):
        """Create the StateGraph workflow for init phase.

        Returns:
            Compiled StateGraph ready for invocation
        """
        workflow = StateGraph(InitState)

        # Nodes
        workflow.add_node("check_refresh", self._check_refresh)
        workflow.add_node("generate_plan", self.initialize_agent)
        workflow.add_node("extract_metadata", self.metadata_agent)
        workflow.add_node("finalize", self._finalize)

        # Edges
        workflow.add_edge(START, "check_refresh")
        workflow.add_conditional_edges(
            "check_refresh",
            self._should_generate_plan,
            {
                "generate": "generate_plan",
                "skip": "extract_metadata",
            },
        )
        workflow.add_conditional_edges(
            "generate_plan",
            self._check_failure_after_agent,
            {
                "continue": "extract_metadata",
                "failed": "finalize",
            },
        )
        workflow.add_conditional_edges(
            "extract_metadata",
            self._check_failure_after_agent,
            {
                "continue": "finalize",
                "failed": "finalize",
            },
        )
        workflow.add_edge("finalize", END)

        return workflow.compile()

    def _check_refresh(self, state: InitState) -> InitState:
        """Check if migration-plan.md exists and pre-load content if in refresh mode.

        Args:
            state: Current init state

        Returns:
            Updated state with migration plan pre-loaded if it exists in refresh mode
        """
        slog = logger.bind(phase="check_refresh", refresh=state.refresh)
        slog.info("Checking refresh mode and migration plan existence")
        migration_plan_path = Path(MIGRATION_PLAN_FILE)

        if state.refresh and migration_plan_path.exists():
            slog.info("Refresh mode: migration plan exists, pre-loading content")
            migration_plan_content = migration_plan_path.read_text()
            return state.update(
                migration_plan_content=migration_plan_content,
                migration_plan_path=MIGRATION_PLAN_FILE,
            )

        return state

    def _should_generate_plan(self, state: InitState) -> Literal["generate", "skip"]:
        """Conditional edge: determine if we should generate plan or skip to metadata.

        Args:
            state: Current init state

        Returns:
            "skip" if refresh mode and plan exists, "generate" otherwise
        """
        slog = logger.bind(phase="should_generate_plan", refresh=state.refresh)
        if state.refresh and Path(MIGRATION_PLAN_FILE).exists():
            slog.info("Refresh mode: Migration plan exists, skipping generation")
            return "skip"

        if state.refresh:
            slog.warning("Refresh mode requested but plan missing, generating new plan")

        return "generate"

    def _check_failure_after_agent(
        self, state: InitState
    ) -> Literal["continue", "failed"]:
        """Conditional edge: check if agent failed.

        Args:
            state: Current init state

        Returns:
            "failed" if agent failed, "continue" otherwise
        """
        slog = logger.bind(phase="check_failure", failed=state.failed)
        if state.failed:
            slog.error(f"Agent failed: {state.failure_reason}")
            return "failed"

        return "continue"

    def _finalize(self, state: InitState) -> InitState:
        """Finalize workflow and log results.

        Args:
            state: Final init state

        Returns:
            Unchanged state (terminal node)
        """
        slog = logger.bind(phase="finalize", failed=state.failed)
        if state.did_fail():
            slog.error("Failing executing the init phase")
            return state

        slog.info("Finalizing init workflow")
        slog.info("Init workflow completed successfully")
        slog.info(f"Migration plan: {state.migration_plan_path}")
        slog.info(
            f"Metadata file: {METADATA_FILENAME} ({len(state.metadata_items)} modules)"
        )
        return state

    def __call__(self, state: InitState) -> InitState:
        """Invoke the init workflow.

        Args:
            state: Initial init state

        Returns:
            Final state after workflow completion
        """
        slog = logger.bind(phase="init_workflow")
        slog.info("Starting init workflow execution")
        result = self._workflow.invoke(state, config=get_runnable_config())
        slog.info("Init workflow execution completed")
        # Convert dict result back to InitState (LangGraph returns dict)
        return InitState(**result)
