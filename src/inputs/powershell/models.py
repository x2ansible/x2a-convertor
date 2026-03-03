"""Powershell execution domain models.

This module defines Pydantic models for representing Powershell script execution flow
and DSC resource configurations. These are pure data structures used for LLM structured outputs.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# ============================================================================
# Script Analysis Models
# ============================================================================


class ScriptExecutionItem(BaseModel):
    """Base execution item for Powershell script operations."""

    type: str
    command: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    condition: str | None = None
    note: str | None = None


class ScriptAnalysisResult(BaseModel):
    """Analysis result for a single Powershell script file."""

    file_path: str
    execution_items: list[ScriptExecutionItem] = Field(default_factory=list)


class ScriptExecutionAnalysis(BaseModel):
    """LLM output for script execution analysis."""

    execution_order: list[ScriptExecutionItem] = Field(
        default_factory=list,
        description="List of execution items in sequence order",
    )


# ============================================================================
# DSC Analysis Models
# ============================================================================


class DSCResourceItem(BaseModel):
    """A single DSC resource declaration."""

    resource_type: str
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    ensure: str = "Present"


class DSCAnalysisResult(BaseModel):
    """Analysis result for a DSC configuration file."""

    file_path: str
    configuration_name: str
    node_name: str = "localhost"
    resources: list[DSCResourceItem] = Field(default_factory=list)


class DSCExecutionAnalysis(BaseModel):
    """LLM output for DSC configuration analysis."""

    configuration_name: str = ""
    node_name: str = "localhost"
    resources: list[DSCResourceItem] = Field(
        default_factory=list,
        description="List of DSC resources in declaration order",
    )


# ============================================================================
# Module Analysis Models
# ============================================================================


class ParameterDefinition(BaseModel):
    """A Powershell parameter definition."""

    name: str
    type: str = "string"
    default_value: Any = None
    mandatory: bool = False
    help_message: str = ""


class ModuleAnalysisResult(BaseModel):
    """Analysis result for a Powershell module file."""

    file_path: str
    exported_functions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    parameters: list[ParameterDefinition] = Field(default_factory=list)


class ModuleExecutionAnalysis(BaseModel):
    """LLM output for module analysis."""

    exported_functions: list[str] = Field(
        default_factory=list,
        description="Functions exported by the module",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Import-Module dependencies",
    )
    parameters: list[ParameterDefinition] = Field(
        default_factory=list,
        description="Parameters defined in the module",
    )


# ============================================================================
# File Classification
# ============================================================================


class FileClassification(BaseModel):
    """Classification of a Powershell file by type."""

    file_path: str
    file_type: Literal["script", "dsc_config", "module", "data", "unknown"]


# ============================================================================
# Aggregate Analysis
# ============================================================================


class PowershellStructuredAnalysis(BaseModel):
    """Aggregate of all structured analysis results from Powershell code.

    Combines analysis from scripts, DSC configs, and modules into
    a single typed structure.
    """

    scripts: list[ScriptAnalysisResult] = Field(default_factory=list)
    dsc_configs: list[DSCAnalysisResult] = Field(default_factory=list)
    modules: list[ModuleAnalysisResult] = Field(default_factory=list)
    parameters: list[ParameterDefinition] = Field(default_factory=list)

    def get_total_files_analyzed(self) -> int:
        """Get total number of files analyzed."""
        return len(self.scripts) + len(self.dsc_configs) + len(self.modules)

    @property
    def analyzed_file_paths(self) -> list[str]:
        """Get all analyzed file paths."""
        files = []
        files.extend(s.file_path for s in self.scripts)
        files.extend(d.file_path for d in self.dsc_configs)
        files.extend(m.file_path for m in self.modules)
        return sorted(set(files))

    @property
    def all_dependencies(self) -> list[str]:
        """Get all Import-Module dependencies across all modules."""
        deps: set[str] = set()
        for module in self.modules:
            deps.update(module.dependencies)
        return sorted(deps)
