"""Powershell infrastructure analyzer.

This package provides analysis of Powershell scripts and DSC configurations
for migration to Ansible.

Public API:
    PowershellSubagent - Main analyzer class implementing InfrastructureAnalyzer protocol
"""

from .analyzer import PowershellSubagent

__all__ = ["PowershellSubagent"]
