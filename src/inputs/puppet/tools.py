"""Puppet-specific tools for analysis agents."""

from langchain_core.tools import BaseTool
from pydantic import Field

from .hiera_parser import HieraConfigParser


class HieraParserTool(BaseTool):
    """Parse hiera.yaml and resolve data files on disk."""

    name: str = "parse_hiera_config"
    description: str = (
        "Parse the hiera.yaml configuration file for a Puppet module. "
        "Returns the hierarchy structure with resolved data file paths. "
        "Use this to understand the Hiera variable hierarchy before analyzing data files."
    )
    module_path: str = Field(description="Path to the Puppet module root")

    def _run(self, *args, **kwargs) -> str:
        parser = HieraConfigParser(self.module_path)
        hierarchy = parser.parse()

        if not hierarchy.levels:
            return "No hiera.yaml found or no hierarchy levels defined."

        lines = [
            f"Hiera v{hierarchy.version} — {len(hierarchy.levels)} levels, "
            f"{hierarchy.total_data_files} data files",
            "",
        ]
        for level in hierarchy.levels:
            lines.append(f"Level: {level.name}")
            lines.append(f"  Pattern: {level.path_pattern}")
            lines.append(f"  Datadir: {level.datadir}")
            if level.resolved_files:
                lines.append(f"  Files ({len(level.resolved_files)}):")
                for f in level.resolved_files:
                    lines.append(f"    - {f}")
            else:
                lines.append("  Files: (none resolved on disk)")
            lines.append("")

        return "\n".join(lines)
