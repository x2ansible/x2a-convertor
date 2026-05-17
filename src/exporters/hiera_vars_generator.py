"""Deterministic Hiera-to-Ansible vars file generator.

Reads the hiera-data-{module}.json produced during the analyze phase and
generates defaults/main.yml + vars/*.yml with exact values from the
original Puppet Hiera data files.  No LLM involved — only key renaming.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.base_agent import BaseAgent
from src.exporters.state import ExportState
from src.types import ChecklistStatus
from src.types.telemetry import AgentMetrics
from src.utils.logging import get_logger

logger = get_logger(__name__)

_COMMON_LEVEL_KEYWORDS = frozenset({"common", "global", "default"})

_ENCRYPTED_PREFIX = "ENC["

_HIERA_METADATA_KEYS = frozenset({"lookup_options"})


class HieraVarsGenerator(BaseAgent[ExportState]):
    """Pre-generate Ansible vars files from Hiera data — no LLM needed."""

    _NAME = "Hiera Vars Generator"

    def execute(self, state: ExportState, metrics: AgentMetrics | None) -> ExportState:
        module_name = str(state.module)
        json_path = Path(state.path).parent / f"hiera-data-{module_name}.json"

        if not json_path.exists():
            self._log.info(f"No {json_path} found, skipping vars generation")
            return state

        hiera_entries = json.loads(json_path.read_text())
        if not hiera_entries:
            self._log.info("Hiera data JSON is empty")
            return state

        ansible_path = Path(state.get_ansible_path())
        generated = 0

        for entry in hiera_entries:
            target = self._target_path(
                entry["hierarchy_level"], entry["file_path"], ansible_path
            )
            if target is None:
                self._log.warning(
                    f"Could not determine target for level "
                    f"'{entry['hierarchy_level']}' ({entry['file_path']})"
                )
                continue

            content = self._transform(
                entry["raw_content"], entry["mappings"], module_name
            )
            if content is None:
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            self._log.info(f"Generated {target}")

            self._mark_complete(state, str(target), entry["file_path"])
            generated += 1

        self._log.info(f"Generated {generated} vars files deterministically")
        if metrics:
            metrics.record_metric("vars_files_generated", generated)

        return state

    # ------------------------------------------------------------------
    # Path routing
    # ------------------------------------------------------------------

    @staticmethod
    def _target_path(level: str, file_path: str, ansible_path: Path) -> Path | None:
        level_words = set(level.lower().split())
        if level_words & _COMMON_LEVEL_KEYWORDS:
            return ansible_path / "defaults" / "main.yml"

        stem = Path(file_path).stem

        return ansible_path / "vars" / f"{stem}.yml"

    # ------------------------------------------------------------------
    # Key transformation
    # ------------------------------------------------------------------

    def _transform(
        self,
        raw_content: str,
        mappings: list[dict],
        module_name: str,
    ) -> str | None:
        if not raw_content.strip():
            return None

        try:
            data = yaml.safe_load(raw_content)
        except yaml.YAMLError as e:
            self._log.warning(f"Failed to parse Hiera YAML: {e}")
            return None

        if not isinstance(data, dict):
            return None

        lookup = {m["puppet_key"]: m for m in mappings}
        prefix = self._detect_prefix(data)

        transformed: dict = {}
        for key, value in data.items():
            if key in _HIERA_METADATA_KEYS:
                continue

            if isinstance(value, str) and value.startswith(_ENCRYPTED_PREFIX):
                continue

            mapping = lookup.get(key)
            if mapping:
                ansible_name = mapping["ansible_variable_name"]
            else:
                ansible_name = self._default_rename(key, prefix, module_name)

            transformed[ansible_name] = value

        if not transformed:
            return None

        dumped = yaml.dump(transformed, default_flow_style=False, sort_keys=False)
        return f"---\n{dumped}"

    @staticmethod
    def _detect_prefix(data: dict) -> str:
        """Detect the Puppet module prefix from keys (e.g., 'profile_haproxy')."""
        for key in data:
            if "::" in key:
                return key.split("::")[0]
        return ""

    @staticmethod
    def _default_rename(key: str, prefix: str, module_name: str) -> str:
        """Fallback rename when no mapping exists."""
        if prefix and key.startswith(f"{prefix}::"):
            bare = key[len(prefix) + 2 :]
        elif "::" in key:
            bare = key.split("::")[-1]
        else:
            bare = key
        role_prefix = module_name.replace("-", "_")
        for strip in ("profile_", "role_"):
            if role_prefix.startswith(strip):
                role_prefix = role_prefix[len(strip) :]
                break
        return f"{role_prefix}_{bare}"

    # ------------------------------------------------------------------
    # Checklist
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_path(path: str) -> str:
        return path.lstrip("./") if path not in ("N/A", "") else path

    def _mark_complete(
        self, state: ExportState, target_path: str, source_path: str
    ) -> None:
        if state.checklist is None:
            return

        norm_target = self._normalize_path(target_path)
        found = False
        for item in state.checklist.items:
            if self._normalize_path(item.target_path) == norm_target:
                state.checklist.update_task(
                    source_path=item.source_path,
                    target_path=item.target_path,
                    status=ChecklistStatus.COMPLETE,
                    notes="Generated deterministically from Hiera data",
                )
                found = True
                break

        if not found:
            state.checklist.add_task(
                category="attributes",
                source_path=source_path,
                target_path=target_path,
                status=ChecklistStatus.COMPLETE,
                description="Generated deterministically from Hiera data",
            )

        state.checklist.save(state.get_checklist_path())
