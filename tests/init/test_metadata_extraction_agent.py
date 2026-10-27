"""Tests for MetadataExtractionAgent."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.const import MODULE_INVENTORY_HEADING
from src.init.init_state import InitState
from src.init.metadata_extraction_agent import MetadataExtractionAgent
from src.types import MetadataCollection, ModuleMetadata


def _module(name: str) -> ModuleMetadata:
    return ModuleMetadata(
        name=name, path=f"cookbooks/{name}", description="d", technology="Chef"
    )


def _state(plan: str) -> InitState:
    return InitState(
        user_message="test",
        path="/tmp/test",
        directory_listing="",
        migration_plan_content=plan,
    )


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return MetadataExtractionAgent(model=MagicMock())


def _run(agent, plan, names):
    agent.invoke_structured = MagicMock(
        return_value=MetadataCollection(modules=[_module(n) for n in names])
    )
    return agent.execute(_state(plan), None), agent.invoke_structured


class TestExtraction:
    def test_agent_forwards_whole_plan_unfiltered(self, agent):
        """The agent sends the plan verbatim; excluding out-of-inventory modules
        is delegated to the LLM, never done in code. Guards against any future
        code-side scoping of the input."""
        plan = (
            "### MODULE INVENTORY\n- cache\n\n"
            "### Infrastructure Files\nfastapi-tutorial is still present"
        )

        _, invoke = _run(agent, plan, ["cache"])

        user_content = invoke.call_args.args[1][-1]["content"]
        assert plan in user_content

    def test_result_is_written_and_technology_detected(self, agent):
        plan = "### MODULE INVENTORY\n- cache\n- nginx-multisite"

        state, _ = _run(agent, plan, ["cache", "nginx-multisite"])

        written = json.loads(Path("generated-project-metadata.json").read_text())
        assert [m["name"] for m in state.metadata_items] == ["cache", "nginx-multisite"]
        assert [m["name"] for m in written] == ["cache", "nginx-multisite"]
        assert state.source_technology.value == "Chef"
        assert not state.failed

    def test_empty_result_marks_state_failed_and_writes_nothing(self, agent):
        plan = "### MODULE INVENTORY\n- cache"

        state, _ = _run(agent, plan, [])

        assert state.failed
        assert not Path("generated-project-metadata.json").exists()


def test_plan_prompt_uses_inventory_heading():
    """The extractor relies on the heading the plan prompt asks for."""
    prompt = (
        Path(__file__).parents[2] / "prompts" / "init_migration_instructions.md"
    ).read_text()

    assert f"### {MODULE_INVENTORY_HEADING}" in prompt
