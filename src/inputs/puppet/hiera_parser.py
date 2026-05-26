"""Deterministic Hiera configuration parser.

Parses hiera.yaml to discover the hierarchy structure and resolve
which data files actually exist on disk. No LLM involved — this is
purely structural (YAML parsing + file globbing).

Supports Hiera v3 and v5 with file-based backends. Known limitations:
- Custom backends (eyaml, vault, etc.) are not resolved — only yaml/json file backends
- mapped_paths entries are not yet supported (uncommon)
- glob entries are treated as standard path patterns

Semantic analysis of file contents is handled by HieraDataAnalysisService.
"""

import re
from pathlib import Path

import yaml

from src.utils.logging import get_logger

from .models import HieraHierarchy, HieraLevel

logger = get_logger(__name__)

HIERA_INTERPOLATION_PATTERN = re.compile(r"%\{[^}]+\}")


class HieraConfigParser:
    """Parse hiera.yaml and resolve data files on disk."""

    def __init__(self, module_path: str):
        self._module_path = Path(module_path)
        self._hiera_config: dict | None = None
        self._hierarchy: HieraHierarchy | None = None

    def parse(self) -> HieraHierarchy:
        if self._hierarchy is not None:
            return self._hierarchy

        config_path = self._find_hiera_config()
        if config_path is None:
            logger.info("No hiera.yaml found, returning empty hierarchy")
            self._hierarchy = HieraHierarchy()
            return self._hierarchy

        logger.info(f"Parsing Hiera config: {config_path}")
        with Path(config_path).open() as f:
            self._hiera_config = yaml.safe_load(f)

        if self._hiera_config is None:
            self._hierarchy = HieraHierarchy()
            return self._hierarchy

        version = self._detect_version()
        if version >= 5:
            self._hierarchy = self._parse_v5(config_path)
        else:
            self._hierarchy = self._parse_v3(config_path)

        logger.info(
            f"Parsed {len(self._hierarchy.levels)} hierarchy levels, "
            f"{self._hierarchy.total_data_files} data files found"
        )
        return self._hierarchy

    def get_data_files_by_level(self) -> dict[str, list[str]]:
        hierarchy = self.parse()
        return {
            level.name: level.resolved_files
            for level in hierarchy.levels
            if level.resolved_files
        }

    def _find_hiera_config(self) -> Path | None:
        candidates = [
            self._module_path / "hiera.yaml",
            self._module_path / "hiera.yml",
        ]
        current = self._module_path.parent
        for _ in range(3):
            candidates.append(current / "hiera.yaml")
            candidates.append(current / "hiera.yml")
            current = current.parent

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _detect_version(self) -> int:
        if self._hiera_config is None:
            return 5
        if "version" in self._hiera_config:
            return int(self._hiera_config["version"])
        if ":hierarchy:" in str(self._hiera_config) or isinstance(
            self._hiera_config.get(":hierarchy:"), list
        ):
            return 3
        return 5

    def _parse_v5(self, config_path: Path) -> HieraHierarchy:
        assert self._hiera_config is not None
        defaults = self._hiera_config.get("defaults", {})
        default_datadir = defaults.get("datadir", "data")
        hierarchy_entries = self._hiera_config.get("hierarchy", [])

        levels: list[HieraLevel] = []
        total_files = 0

        for entry in hierarchy_entries:
            name = entry.get("name", "unnamed")
            datadir = entry.get("datadir", default_datadir)
            paths = entry.get("paths", [])
            if not paths and "path" in entry:
                paths = [entry["path"]]

            for path_pattern in paths:
                base_path = config_path.parent / datadir
                resolved = self._resolve_data_files(path_pattern, base_path)
                total_files += len(resolved)
                levels.append(
                    HieraLevel(
                        name=name,
                        path_pattern=path_pattern,
                        datadir=datadir,
                        resolved_files=resolved,
                    )
                )

        return HieraHierarchy(
            version=5,
            defaults=defaults,
            levels=levels,
            total_data_files=total_files,
        )

    def _parse_v3(self, config_path: Path) -> HieraHierarchy:
        assert self._hiera_config is not None
        hierarchy_list = self._hiera_config.get(":hierarchy:", [])
        if isinstance(hierarchy_list, str):
            hierarchy_list = [hierarchy_list]

        datadir = self._hiera_config.get(":yaml:", {}).get(":datadir:", "data")
        if isinstance(datadir, str) and datadir.startswith("/"):
            datadir = "data"

        levels: list[HieraLevel] = []
        total_files = 0

        for idx, entry in enumerate(hierarchy_list):
            path_pattern = f"{entry}.yaml"
            base_path = config_path.parent / datadir
            resolved = self._resolve_data_files(path_pattern, base_path)
            total_files += len(resolved)
            levels.append(
                HieraLevel(
                    name=f"Level {idx + 1}: {entry}",
                    path_pattern=path_pattern,
                    datadir=datadir,
                    resolved_files=resolved,
                )
            )

        return HieraHierarchy(
            version=3,
            defaults={},
            levels=levels,
            total_data_files=total_files,
        )

    def _resolve_data_files(self, path_pattern: str, base_path: Path) -> list[str]:
        glob_pattern = HIERA_INTERPOLATION_PATTERN.sub("*", path_pattern)
        resolved: list[str] = []
        try:
            for match in base_path.glob(glob_pattern):
                if match.is_file():
                    resolved.append(str(match))
        except Exception as e:
            logger.warning(f"Failed to glob {glob_pattern} in {base_path}: {e}")
        return sorted(resolved)
