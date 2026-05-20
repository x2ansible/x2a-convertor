"""State for per-file analysis by InputAgent services.

Wraps a single file path so that services can be invoked
via the standard ``service(file_state)`` pattern with
automatic telemetry from BaseAgent.__call__.
"""

from dataclasses import dataclass, field, replace
from typing import Any

from src.types.base_state import BaseState


@dataclass
class FileAnalysisState(BaseState):
    """State carrying a single file path and its analysis result.

    Attributes:
        result: Typed analysis output produced by the service
                (e.g. RecipeExecutionAnalysis, DSCExecutionAnalysis).
    """

    result: Any = field(default=None, kw_only=True)

    def update(self, **kwargs) -> "FileAnalysisState":
        return replace(self, **kwargs)

    def mark_failed(self, reason: str) -> "FileAnalysisState":
        return self.update(failed=True, failure_reason=reason)
