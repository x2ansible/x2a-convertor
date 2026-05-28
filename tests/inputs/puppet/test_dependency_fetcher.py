"""Tests for Puppet dependency fetcher (Puppetfile parser)."""

import shutil
from pathlib import Path

import pytest

from src.inputs.puppet.dependency_fetcher import PuppetDependencyFetcher

PUPPET_EXAMPLES_DIR = Path(__file__).resolve().parents[3] / ".." / "puppet-examples"
HAPROXY_MODULE = PUPPET_EXAMPLES_DIR / "site" / "modules" / "linux" / "profile_haproxy"

has_r10k = shutil.which("r10k") is not None
has_puppet_examples = (
    HAPROXY_MODULE.exists() and (HAPROXY_MODULE / "Puppetfile").exists()
)


class TestPuppetDependencyFetcher:
    """Test Puppetfile parsing via tree-sitter."""

    def test_no_puppetfile(self, tmp_path):
        fetcher = PuppetDependencyFetcher(str(tmp_path))
        has_deps, deps = fetcher.has_dependencies()
        assert has_deps is False
        assert deps == []

    def test_empty_puppetfile(self, tmp_path):
        (tmp_path / "Puppetfile").write_text("")
        fetcher = PuppetDependencyFetcher(str(tmp_path))
        has_deps, deps = fetcher.has_dependencies()
        assert has_deps is False
        assert deps == []

    def test_forge_modules(self, tmp_path):
        puppetfile = """
mod 'puppetlabs-stdlib', '9.7.0'
mod 'puppetlabs-concat', '9.0.2'
mod 'puppetlabs-firewall', '8.1.3'
"""
        (tmp_path / "Puppetfile").write_text(puppetfile)
        fetcher = PuppetDependencyFetcher(str(tmp_path))

        has_deps, dep_names = fetcher.has_dependencies()
        assert has_deps is True
        assert len(dep_names) == 3
        assert "puppetlabs-stdlib" in dep_names
        assert "puppetlabs-concat" in dep_names

    def test_forge_module_details(self, tmp_path):
        puppetfile = "mod 'puppetlabs-stdlib', '9.7.0'\n"
        (tmp_path / "Puppetfile").write_text(puppetfile)
        fetcher = PuppetDependencyFetcher(str(tmp_path))

        deps = fetcher.get_dependency_info()
        assert len(deps) == 1
        assert deps[0]["name"] == "puppetlabs-stdlib"
        assert deps[0]["source"] == "forge"
        assert deps[0]["version"] == "9.7.0"

    def test_forge_module_no_version(self, tmp_path):
        puppetfile = "mod 'puppetlabs-stdlib'\n"
        (tmp_path / "Puppetfile").write_text(puppetfile)
        fetcher = PuppetDependencyFetcher(str(tmp_path))

        deps = fetcher.get_dependency_info()
        assert len(deps) == 1
        assert deps[0]["name"] == "puppetlabs-stdlib"
        assert deps[0]["version"] == ""

    def test_git_module(self, tmp_path):
        puppetfile = """
mod 'custom_module',
  :git => 'https://github.com/example/custom_module.git',
  :tag => 'v1.2.0'
"""
        (tmp_path / "Puppetfile").write_text(puppetfile)
        fetcher = PuppetDependencyFetcher(str(tmp_path))

        deps = fetcher.get_dependency_info()
        assert len(deps) == 1
        assert deps[0]["name"] == "custom_module"
        assert deps[0]["source"] == "git"
        assert deps[0]["url"] == "https://github.com/example/custom_module.git"
        assert deps[0]["version"] == "v1.2.0"

    def test_git_module_with_branch(self, tmp_path):
        puppetfile = """
mod 'my_module',
  :git => 'https://git.example.com/my_module.git',
  :branch => 'main'
"""
        (tmp_path / "Puppetfile").write_text(puppetfile)
        fetcher = PuppetDependencyFetcher(str(tmp_path))

        deps = fetcher.get_dependency_info()
        assert len(deps) == 1
        assert deps[0]["version"] == "main"

    def test_git_module_with_ref(self, tmp_path):
        puppetfile = """
mod 'my_module',
  :git => 'https://git.example.com/my_module.git',
  :ref => 'abc123'
"""
        (tmp_path / "Puppetfile").write_text(puppetfile)
        fetcher = PuppetDependencyFetcher(str(tmp_path))

        deps = fetcher.get_dependency_info()
        assert len(deps) == 1
        assert deps[0]["version"] == "abc123"

    def test_mixed_forge_and_git(self, tmp_path):
        puppetfile = """
mod 'puppetlabs-stdlib', '9.7.0'
mod 'custom_module',
  :git => 'https://github.com/example/custom_module.git',
  :tag => 'v2.0.0'
mod 'puppetlabs-concat', '9.0.2'
"""
        (tmp_path / "Puppetfile").write_text(puppetfile)
        fetcher = PuppetDependencyFetcher(str(tmp_path))

        deps = fetcher.get_dependency_info()
        assert len(deps) == 3
        forge_deps = [d for d in deps if d["source"] == "forge"]
        git_deps = [d for d in deps if d["source"] == "git"]
        assert len(forge_deps) == 2
        assert len(git_deps) == 1

    def test_caching(self, tmp_path):
        puppetfile = "mod 'puppetlabs-stdlib', '9.0.0'\n"
        (tmp_path / "Puppetfile").write_text(puppetfile)
        fetcher = PuppetDependencyFetcher(str(tmp_path))

        deps1 = fetcher.get_dependency_info()
        deps2 = fetcher.get_dependency_info()
        assert deps1 is deps2

    def test_git_overrides_forge_duplicate(self, tmp_path):
        """When a module appears as both forge and git, git takes priority."""
        puppetfile = """
mod 'stdlib', '9.0.0'
mod 'stdlib',
  :git => 'https://github.com/custom/stdlib.git',
  :tag => 'custom-v1'
"""
        (tmp_path / "Puppetfile").write_text(puppetfile)
        fetcher = PuppetDependencyFetcher(str(tmp_path))

        deps = fetcher.get_dependency_info()
        stdlib_deps = [d for d in deps if d["name"] == "stdlib"]
        assert len(stdlib_deps) == 1
        assert stdlib_deps[0]["source"] == "git"

    def test_comments_and_blank_lines(self, tmp_path):
        puppetfile = """
# This is a comment
mod 'puppetlabs-stdlib', '9.0.0'

# Another comment
mod 'puppetlabs-concat', '9.0.2'
"""
        (tmp_path / "Puppetfile").write_text(puppetfile)
        fetcher = PuppetDependencyFetcher(str(tmp_path))

        deps = fetcher.get_dependency_info()
        assert len(deps) == 2


@pytest.mark.skipif(
    not (has_r10k and has_puppet_examples),
    reason="Requires r10k and puppet-examples repo with Puppetfile",
)
class TestDependencyFetcherIntegration:
    """Integration tests using real puppet-examples and r10k."""

    def test_parse_real_puppetfile(self):
        fetcher = PuppetDependencyFetcher(str(HAPROXY_MODULE))
        has_deps, names = fetcher.has_dependencies()
        assert has_deps is True
        assert len(names) >= 3
        assert "puppetlabs-stdlib" in names
        assert "puppetlabs-concat" in names
        assert "puppetlabs-firewall" in names

    def test_dependency_info_details(self):
        fetcher = PuppetDependencyFetcher(str(HAPROXY_MODULE))
        deps = fetcher.get_dependency_info()

        stdlib = next(d for d in deps if d["name"] == "puppetlabs-stdlib")
        assert stdlib["source"] == "forge"
        assert stdlib["version"] == "9.7.0"

        concat = next(d for d in deps if d["name"] == "puppetlabs-concat")
        assert concat["source"] == "forge"
        assert concat["version"] == "9.0.2"

    def test_download_dependencies(self, tmp_path):
        """Test actual r10k download into a temp directory."""
        test_dir = tmp_path / "test_module"
        test_dir.mkdir()
        puppetfile_content = (HAPROXY_MODULE / "Puppetfile").read_text()
        (test_dir / "Puppetfile").write_text(puppetfile_content)

        fetcher = PuppetDependencyFetcher(str(test_dir))
        deps_path = fetcher.download_dependencies()

        assert deps_path is not None
        assert deps_path.exists()
        downloaded = [d.name for d in deps_path.iterdir()]
        assert "stdlib" in downloaded
        assert "concat" in downloaded
        assert "firewall" in downloaded
