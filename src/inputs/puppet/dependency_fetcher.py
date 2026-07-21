"""Puppet dependency fetcher agent.

Parses Puppetfile to catalog external module dependencies and
downloads them using r10k for analysis.
"""

import shutil
import subprocess

from prompts.get_prompt import get_prompt
from src.inputs.input_agent import InputAgent
from src.inputs.puppet.models import PuppetDependencyList
from src.inputs.puppet.state import PuppetState
from src.types.document import DocumentFile
from src.types.telemetry import AgentMetrics
from src.utils.logging import get_logger
from src.utils.path import Path

logger = get_logger(__name__)

_VERSION_SYMBOLS = frozenset({":tag", ":ref", ":branch"})

DEPENDENCIES_DIR = "migration-dependencies"


def resolve_puppet_module_root(path: str) -> Path:
    """Resolve path to Puppet module root directory.

    The module selector may return 'manifests/init.pp' or 'manifests'
    instead of the module root. Walk up to find the directory containing manifests/.
    """
    p = Path(path).resolve()
    if p.is_file():
        p = p.parent
    for candidate in [p, *list(p.parents)]:
        if (candidate / "manifests").is_dir():
            return candidate
    return Path(path).resolve()


class PuppetDependencyAgent(InputAgent[PuppetState]):
    """Fetch and parse Puppet module dependencies from Puppetfile.

    Workflow:
    1. Find Puppetfile (walk up from module path)
    2. Parse dependencies using tree-sitter Ruby parser
    3. Download to migration-dependencies/ using r10k
    4. Return updated state with typed dependencies
    """

    _NAME = "Puppet Dependency Fetcher"

    SYSTEM_PROMPT = "puppet_dependency_fetcher_system"
    USER_PROMPT = "puppet_dependency_fetcher_task"

    def __init__(self, model=None):
        super().__init__(model)

    def _build_messages(
        self, puppetfile_doc: str, dependencies_path: str
    ) -> list[dict[str, str]]:
        system_message = get_prompt(self.SYSTEM_PROMPT).format()

        user_prompt = get_prompt(self.USER_PROMPT).format(
            puppetfile=puppetfile_doc, dependencies_path=dependencies_path
        )

        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]

    def execute(self, state: PuppetState, metrics: AgentMetrics | None) -> PuppetState:
        module_root = resolve_puppet_module_root(state.path)
        puppetfile = self._find_puppetfile(module_root)

        if not puppetfile:
            self._log.info("No Puppetfile found or no dependencies")
            if metrics:
                metrics.record_metric("dependencies_found", 0)
            return state.update(dependencies=[])

        deps_path = self._download_dependencies(puppetfile, module_root)

        if not deps_path:
            self._log.warning("Dependency download failed, no dependencies available")
            if metrics:
                metrics.record_metric("dependencies_found", 0)
            return state.update(dependencies=[])

        puppetfile_doc = DocumentFile.from_path(puppetfile)
        messages = self._build_messages(puppetfile_doc.to_document(), str(deps_path))

        result = self.invoke_structured(PuppetDependencyList, messages, metrics)
        if not result:
            self._log.error("Failed to parse dependencies from LLM response")
            if metrics:
                metrics.record_metric("dependencies_found", 0)
            return state.update(dependencies=[])

        dependencies = result.dependencies
        self._log.info(f"Parsed {len(dependencies)} dependencies from Puppetfile")

        if metrics:
            metrics.record_metric("dependencies_found", len(dependencies))

        return state.update(dependencies=dependencies, dependencies_dir=str(deps_path))

    def _download_dependencies(
        self, puppetfile: Path, module_root: Path
    ) -> Path | None:
        deps_dir = puppetfile.parent / DEPENDENCIES_DIR

        if not shutil.which("r10k"):
            self._log.warning(
                "r10k not found in PATH -- cannot download dependencies. "
                "Install with: gem install r10k"
            )
            return None

        deps_dir.mkdir(exist_ok=True)
        return self._run_r10k(puppetfile, deps_dir, module_root)

    def _run_r10k(
        self, puppetfile: Path, deps_dir: Path, module_root: Path
    ) -> Path | None:
        cmd = [
            "r10k",
            "puppetfile",
            "install",
            "--puppetfile",
            str(puppetfile),
            "--moduledir",
            str(deps_dir),
        ]

        try:
            self._log.info(f"Downloading dependencies to {deps_dir}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(module_root),
            )
            if result.returncode != 0:
                self._log.error(f"r10k failed: {result.stderr}")
                return None
            self._log.info(f"Dependencies downloaded to {deps_dir}")
            return deps_dir
        except subprocess.TimeoutExpired:
            self._log.error("r10k timed out after 300s")
            return None
        except Exception as e:
            self._log.error(f"Failed to run r10k: {e}")
            return None

    @staticmethod
    def _find_puppetfile(start: Path) -> Path | None:
        """Walk up from start to find Puppetfile."""
        for candidate in [start, *list(start.parents)]:
            pf = candidate / "Puppetfile"
            if pf.is_file():
                return pf
            if candidate == candidate.parent:
                break
        return None
