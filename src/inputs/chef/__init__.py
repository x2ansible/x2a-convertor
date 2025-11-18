"""Chef infrastructure analyzer.

This package provides a clean, SOLID-based architecture for analyzing Chef cookbooks
and generating migration specifications.

Public API:
    ChefSubagent - Main analyzer class implementing InfrastructureAnalyzer protocol
    ChefDependencyManager - Handles Chef dependency fetching
"""

from .analyzer import ChefAgentError, ChefSubagent
from .dependency_fetcher import ChefDependencyManager

__all__ = ["ChefAgentError", "ChefDependencyManager", "ChefSubagent"]
