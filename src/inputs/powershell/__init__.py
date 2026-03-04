"""PowerShell infrastructure analyzer.

This package provides analysis of PowerShell scripts and DSC configurations
for migration to Ansible.

Public API:
    PowerShellSubagent - Main analyzer class implementing InfrastructureAnalyzer protocol
"""

from .analyzer import PowerShellSubagent

__all__ = ["PowerShellSubagent"]
