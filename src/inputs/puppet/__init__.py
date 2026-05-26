"""Puppet infrastructure analyzer.

This package provides analysis of Puppet modules
and generation of migration specifications.

Public API:
    PuppetSubagent - Main analyzer class implementing InfrastructureAnalyzer protocol
"""

from .analyzer import PuppetSubagent

__all__ = ["PuppetSubagent"]
