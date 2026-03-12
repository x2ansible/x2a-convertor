"""Ansible role domain models.

This module defines Pydantic models for representing Ansible role execution structure.
These are pure data structures used for LLM structured outputs.
"""

from typing import Any

from pydantic import BaseModel, Field

# ============================================================================
# Task Execution Models
# ============================================================================


class TaskExecution(BaseModel):
    """A single Ansible task extracted from a tasks/handlers file."""

    name: str = ""
    module: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    loop: str | None = None
    condition: str | None = None
    notify: list[str] = Field(default_factory=list)
    privilege_escalation: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None
    extra_directives: dict[str, Any] = Field(default_factory=dict)


class TaskFileExecutionAnalysis(BaseModel):
    """LLM output: execution analysis of a tasks/handlers YAML file."""

    tasks: list[TaskExecution] = Field(default_factory=list)


class TaskFileAnalysisResult(BaseModel):
    """Stored result for a task/handler file."""

    file_path: str
    file_type: str = "tasks"
    analysis: TaskFileExecutionAnalysis


# ============================================================================
# Variables/Defaults Models
# ============================================================================


class VariablesAnalysis(BaseModel):
    """LLM output: analysis of defaults/vars YAML file."""

    variables: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class VariablesAnalysisResult(BaseModel):
    """Stored result for a defaults/vars file."""

    file_path: str
    file_type: str = "defaults"
    analysis: VariablesAnalysis


# ============================================================================
# Meta Models
# ============================================================================


class MetaAnalysis(BaseModel):
    """LLM output: analysis of meta/main.yml."""

    role_name: str = ""
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    platforms: list[dict[str, Any]] = Field(default_factory=list)
    galaxy_info: dict[str, Any] = Field(default_factory=dict)


class MetaAnalysisResult(BaseModel):
    """Stored result for meta/main.yml."""

    file_path: str
    analysis: MetaAnalysis


# ============================================================================
# Template Models
# ============================================================================


class TemplateAnalysis(BaseModel):
    """LLM output: analysis of a .j2 template file."""

    variables_used: list[str] = Field(default_factory=list)
    bare_variables: list[str] = Field(default_factory=list)
    deprecated_tests: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TemplateAnalysisResult(BaseModel):
    """Stored result for a template file."""

    file_path: str
    analysis: TemplateAnalysis


# ============================================================================
# Aggregate Analysis
# ============================================================================


class AnsibleStructuredAnalysis(BaseModel):
    """Aggregate of all role analysis results."""

    tasks_files: list[TaskFileAnalysisResult] = Field(default_factory=list)
    handlers_files: list[TaskFileAnalysisResult] = Field(default_factory=list)
    defaults_files: list[VariablesAnalysisResult] = Field(default_factory=list)
    vars_files: list[VariablesAnalysisResult] = Field(default_factory=list)
    meta: MetaAnalysisResult | None = None
    templates: list[TemplateAnalysisResult] = Field(default_factory=list)
    static_files: list[str] = Field(default_factory=list)

    def get_total_files_analyzed(self) -> int:
        """Get total number of files analyzed."""
        return (
            len(self.tasks_files)
            + len(self.handlers_files)
            + len(self.defaults_files)
            + len(self.vars_files)
            + (1 if self.meta else 0)
            + len(self.templates)
        )

    @property
    def analyzed_file_paths(self) -> list[str]:
        """Get all analyzed file paths."""
        files: list[str] = []
        files.extend(t.file_path for t in self.tasks_files)
        files.extend(h.file_path for h in self.handlers_files)
        files.extend(d.file_path for d in self.defaults_files)
        files.extend(v.file_path for v in self.vars_files)
        if self.meta:
            files.append(self.meta.file_path)
        files.extend(t.file_path for t in self.templates)
        files.extend(self.static_files)
        return sorted(set(files))
