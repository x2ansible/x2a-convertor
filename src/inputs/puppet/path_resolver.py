"""Puppet path resolution service.

Resolves Puppet class names to manifest file paths across a control repo.
Analogous to src/inputs/chef/path_resolver.py.
"""

import re
from pathlib import Path

from src.utils.logging import get_logger

logger = get_logger(__name__)

_INCLUDE_PATTERNS = [
    re.compile(r"""(?:include|contain|require)\s+::?(\S+)"""),
    re.compile(r"""class\s*\{\s*['"]([^'"]+)['"]\s*:"""),
]


class PuppetPathResolver:
    """Resolves Puppet class names to manifest file paths across a control repo.

    Searches modulepath entries (parsed from environment.conf) to locate
    .pp manifest files for any fully-qualified Puppet class name.
    """

    def __init__(self, control_repo_root: Path, modulepath: list[Path]):
        self.root = control_repo_root
        self.modulepath = modulepath

    @staticmethod
    def find_control_repo_root(start_path: Path) -> Path | None:
        """Walk up from start_path looking for environment.conf."""
        p = start_path.resolve()
        if p.is_file():
            p = p.parent
        for candidate in [p, *list(p.parents)]:
            if (candidate / "environment.conf").is_file():
                return candidate
            if candidate == candidate.parent:
                break
        return None

    @staticmethod
    def parse_modulepath(env_conf_path: Path) -> list[Path]:
        """Parse modulepath from environment.conf, return resolved absolute paths.

        Skips entries containing $ (e.g., $basemodulepath) since those
        reference Puppet server internals we can't resolve.
        """
        repo_root = env_conf_path.parent
        result: list[Path] = []

        try:
            content = env_conf_path.read_text()
        except OSError:
            return result

        for line in content.splitlines():
            line = line.strip()
            if not line.startswith("modulepath"):
                continue
            _, _, value = line.partition("=")
            value = value.strip()
            for entry in value.split(":"):
                entry = entry.strip()
                if not entry or "$" in entry:
                    continue
                resolved = (repo_root / entry).resolve()
                if resolved.is_dir():
                    result.append(resolved)
            break

        return result

    def resolve_class(self, class_name: str) -> Path | None:
        """Resolve a Puppet class name to its manifest .pp file path.

        Puppet convention:
          'profile::loadbalancer::haproxy'
            → module = 'profile'
            → manifest = 'manifests/loadbalancer/haproxy.pp'

          'profile_haproxy' (single segment)
            → module = 'profile_haproxy'
            → manifest = 'manifests/init.pp'
        """
        parts = class_name.lstrip(":").split("::")
        module_name = parts[0]

        if len(parts) == 1:
            manifest_rel = Path("manifests") / "init.pp"
        else:
            manifest_rel = Path("manifests") / "/".join(parts[1:])
            manifest_rel = manifest_rel.with_suffix(".pp")

        for mp_entry in self.modulepath:
            candidate = mp_entry / module_name / manifest_rel
            if candidate.is_file():
                return candidate

        return None

    def find_referencing_manifests(self, module_name: str) -> list[Path]:
        """Find .pp files across the modulepath that reference this module.

        Searches for include/contain/require/class declarations that
        reference the given module name. Used to discover roles and
        profiles that form the chain above the target module.

        Skips manifests inside the module itself.
        """
        results: list[Path] = []
        found: set[Path] = set()

        for mp_entry in self.modulepath:
            if not mp_entry.is_dir():
                continue
            for pp_file in mp_entry.glob("**/manifests/**/*.pp"):
                resolved = pp_file.resolve()
                if resolved in found:
                    continue

                if self._file_is_inside_module(pp_file, module_name):
                    continue

                if self._file_references_module(pp_file, module_name):
                    found.add(resolved)
                    results.append(pp_file)
                    self._follow_referencing_chain(pp_file, results, found)

        return sorted(set(results))

    def _file_is_inside_module(self, pp_file: Path, module_name: str) -> bool:
        """Check if a .pp file belongs to the given module."""
        for mp_entry in self.modulepath:
            module_dir = mp_entry / module_name
            try:
                pp_file.resolve().relative_to(module_dir.resolve())
                return True
            except ValueError:
                continue
        return False

    def _file_references_module(self, pp_file: Path, module_name: str) -> bool:
        """Check if a .pp file contains references to the given module."""
        try:
            content = pp_file.read_text()
        except OSError:
            return False

        for pattern in _INCLUDE_PATTERNS:
            for match in pattern.finditer(content):
                referenced = match.group(1).lstrip(":")
                ref_module = referenced.split("::")[0]
                if ref_module == module_name:
                    return True

        return False

    def _follow_referencing_chain(
        self, pp_file: Path, results: list[Path], seen: set[Path]
    ) -> None:
        """Given a file that references our module, find what references IT.

        This discovers the chain: role references profile, profile references module.
        """
        class_name = self._infer_class_name(pp_file)
        if not class_name:
            return

        ref_module = class_name.split("::")[0]

        for mp_entry in self.modulepath:
            if not mp_entry.is_dir():
                continue
            for candidate in mp_entry.glob("**/manifests/**/*.pp"):
                resolved = candidate.resolve()
                if resolved in seen:
                    continue

                if self._file_references_module(candidate, ref_module):
                    seen.add(resolved)
                    results.append(candidate)
                    self._follow_referencing_chain(candidate, results, seen)

    def _infer_class_name(self, pp_file: Path) -> str | None:
        """Infer the Puppet class name from a manifest file path.

        manifests/init.pp → module_name
        manifests/loadbalancer/haproxy.pp → module_name::loadbalancer::haproxy
        """
        for mp_entry in self.modulepath:
            try:
                rel = pp_file.resolve().relative_to(mp_entry.resolve())
            except ValueError:
                continue

            parts = list(rel.parts)
            if len(parts) < 2 or "manifests" not in parts:
                continue

            module_name = parts[0]
            manifests_idx = parts.index("manifests")
            after_manifests = parts[manifests_idx + 1 :]

            if not after_manifests:
                continue

            last = after_manifests[-1]
            if last.endswith(".pp"):
                after_manifests[-1] = last[:-3]

            if after_manifests == ["init"]:
                return module_name

            return "::".join([module_name, *after_manifests])

        return None
