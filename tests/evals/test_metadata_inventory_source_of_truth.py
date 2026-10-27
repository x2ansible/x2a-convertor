"""Evaluation test: MODULE INVENTORY is the single source of truth (PR #313).

Regression coverage for the `init --refresh` bug where a module removed by hand
from the MODULE INVENTORY section of the migration plan was still returned by
the MetadataExtractionAgent (because it is still mentioned elsewhere in the
plan), so the Backstage UI never dropped it.

The fix relies on the extraction prompt: the whole plan is sent to the LLM, and
the LLM is instructed to return only MODULE INVENTORY entries, excluding modules
mentioned only elsewhere. This is verifiable only with a live LLM, hence an eval.

These are eval tests: they require a live LLM and are non-deterministic.
"""

import json
import os
from pathlib import Path

import pytest

from src.init.init_state import InitState
from src.init.metadata_extraction_agent import MetadataExtractionAgent

FIXTURE = (
    Path(__file__).parents[1]
    / "init"
    / "fixtures"
    / "migration-plan-inventory-removed.md"
)


def _has_valid_api_config() -> bool:
    """Check if any supported LLM provider is configured."""
    if os.getenv("OPENAI_API_BASE") and os.getenv("OPENAI_API_KEY"):
        return True
    if os.getenv("ANTHROPIC_API_KEY"):
        return True
    if os.getenv("GEMINI_API_KEY"):
        return True
    model = os.getenv("LLM_MODEL", "")
    if model.startswith("vertex_ai/") and os.getenv("VERTEXAI_PROJECT"):
        return True
    return bool(
        model.startswith("bedrock/")
        and (
            os.getenv("AWS_BEARER_TOKEN_BEDROCK")
            or os.getenv("AWS_ACCESS_KEY_ID")
            or os.getenv("AWS_PROFILE")
        )
    )


pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not _has_valid_api_config(),
        reason="No LLM provider configured (OPENAI_API_BASE+OPENAI_API_KEY, "
        "ANTHROPIC_API_KEY, GEMINI_API_KEY, or vertex_ai LLM_MODEL+VERTEXAI_PROJECT)",
    ),
]


def test_module_outside_inventory_is_excluded(tmp_path, monkeypatch):
    """`fastapi-tutorial` is mentioned only outside MODULE INVENTORY; drop it."""
    monkeypatch.chdir(tmp_path)
    state = InitState(
        user_message="extract metadata",
        path=str(tmp_path),
        directory_listing="",
        migration_plan_content=FIXTURE.read_text(),
    )

    result = MetadataExtractionAgent().execute(state, None)

    assert not result.failed
    names = {m["name"].lower() for m in result.metadata_items}
    assert "cache" in names
    assert "nginx-multisite" in names
    assert not any("fastapi" in name for name in names)

    written = json.loads(Path("generated-project-metadata.json").read_text())
    assert not any("fastapi" in m["name"].lower() for m in written)
