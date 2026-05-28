"""Tests for Puppet path resolver."""

from pathlib import Path

import pytest

from src.inputs.puppet.path_resolver import PuppetPathResolver


@pytest.fixture()
def control_repo(tmp_path):
    """Create a minimal control repo structure for testing."""
    # environment.conf
    (tmp_path / "environment.conf").write_text(
        "modulepath = site/modules/linux:site/modules/common:site:modules\n"
    )

    # modulepath directories
    linux_dir = tmp_path / "site" / "modules" / "linux"
    common_dir = tmp_path / "site" / "modules" / "common"
    site_dir = tmp_path / "site"

    # Module: profile_haproxy
    haproxy_mod = linux_dir / "profile_haproxy" / "manifests"
    haproxy_mod.mkdir(parents=True)
    (haproxy_mod / "init.pp").write_text("class profile_haproxy { }\n")
    (haproxy_mod / "config.pp").write_text("class profile_haproxy::config { }\n")
    (haproxy_mod / "install.pp").write_text("class profile_haproxy::install { }\n")

    # Module: base_utils
    utils_mod = common_dir / "base_utils" / "manifests"
    utils_mod.mkdir(parents=True)
    (utils_mod / "init.pp").write_text("class base_utils { }\n")

    # Profile
    profile_dir = site_dir / "profile" / "manifests" / "loadbalancer"
    profile_dir.mkdir(parents=True)
    (profile_dir / "haproxy.pp").write_text(
        "class profile::loadbalancer::haproxy {\n"
        "  class { 'profile_haproxy': }\n"
        "}\n"
    )

    # Base profile
    base_dir = site_dir / "profile" / "manifests" / "base"
    base_dir.mkdir(parents=True)
    (base_dir / "base.pp").write_text(
        "class profile::base::base {\n"
        "  include base_utils\n"
        "}\n"
    )

    # Role
    role_dir = site_dir / "role" / "manifests"
    role_dir.mkdir(parents=True)
    (role_dir / "haproxy.pp").write_text(
        "class role::haproxy {\n"
        "  include ::profile::base::base\n"
        "  contain ::profile::loadbalancer::haproxy\n"
        "}\n"
    )

    # modules/ dir (empty, for external deps)
    (tmp_path / "modules").mkdir()

    return tmp_path


class TestFindControlRepoRoot:
    def test_found_from_module_path(self, control_repo):
        module_path = (
            control_repo / "site" / "modules" / "linux" / "profile_haproxy"
        )
        root = PuppetPathResolver.find_control_repo_root(module_path)
        assert root == control_repo

    def test_found_from_manifest_file(self, control_repo):
        manifest = (
            control_repo
            / "site"
            / "modules"
            / "linux"
            / "profile_haproxy"
            / "manifests"
            / "init.pp"
        )
        root = PuppetPathResolver.find_control_repo_root(manifest)
        assert root == control_repo

    def test_not_found(self, tmp_path):
        root = PuppetPathResolver.find_control_repo_root(tmp_path)
        assert root is None

    def test_found_at_root(self, control_repo):
        root = PuppetPathResolver.find_control_repo_root(control_repo)
        assert root == control_repo


class TestParseModulepath:
    def test_parse_standard_modulepath(self, control_repo):
        env_conf = control_repo / "environment.conf"
        paths = PuppetPathResolver.parse_modulepath(env_conf)

        path_strs = [str(p) for p in paths]
        assert any("site/modules/linux" in s for s in path_strs)
        assert any("site/modules/common" in s for s in path_strs)
        assert any(s.endswith("/site") for s in path_strs)

    def test_skips_basemodulepath(self, control_repo):
        env_conf = control_repo / "environment.conf"
        paths = PuppetPathResolver.parse_modulepath(env_conf)
        for p in paths:
            assert "$" not in str(p)

    def test_skips_nonexistent_dirs(self, tmp_path):
        (tmp_path / "environment.conf").write_text(
            "modulepath = nonexistent:also_missing\n"
        )
        paths = PuppetPathResolver.parse_modulepath(tmp_path / "environment.conf")
        assert paths == []

    def test_missing_file(self, tmp_path):
        paths = PuppetPathResolver.parse_modulepath(tmp_path / "nope.conf")
        assert paths == []


class TestResolveClass:
    @pytest.fixture()
    def resolver(self, control_repo):
        env_conf = control_repo / "environment.conf"
        modulepath = PuppetPathResolver.parse_modulepath(env_conf)
        return PuppetPathResolver(control_repo, modulepath)

    def test_single_segment_class(self, resolver, control_repo):
        result = resolver.resolve_class("profile_haproxy")
        assert result is not None
        assert result.name == "init.pp"
        assert "profile_haproxy" in str(result)

    def test_multi_segment_class(self, resolver, control_repo):
        result = resolver.resolve_class("profile::loadbalancer::haproxy")
        assert result is not None
        assert result.name == "haproxy.pp"
        assert "profile/manifests/loadbalancer" in str(result)

    def test_subclass(self, resolver):
        result = resolver.resolve_class("profile_haproxy::config")
        assert result is not None
        assert result.name == "config.pp"

    def test_not_found(self, resolver):
        result = resolver.resolve_class("nonexistent::missing")
        assert result is None

    def test_strips_leading_colons(self, resolver):
        result = resolver.resolve_class("::profile_haproxy")
        assert result is not None

    def test_base_utils(self, resolver):
        result = resolver.resolve_class("base_utils")
        assert result is not None
        assert "base_utils" in str(result)

    def test_role_class(self, resolver):
        result = resolver.resolve_class("role::haproxy")
        assert result is not None
        assert result.name == "haproxy.pp"

    def test_base_profile(self, resolver):
        result = resolver.resolve_class("profile::base::base")
        assert result is not None
        assert result.name == "base.pp"


class TestFindReferencingManifests:
    @pytest.fixture()
    def resolver(self, control_repo):
        env_conf = control_repo / "environment.conf"
        modulepath = PuppetPathResolver.parse_modulepath(env_conf)
        return PuppetPathResolver(control_repo, modulepath)

    def test_finds_profile_and_role(self, resolver):
        results = resolver.find_referencing_manifests("profile_haproxy")
        filenames = [p.name for p in results]
        assert "haproxy.pp" in filenames
        assert len(results) >= 2

    def test_finds_chain_upward(self, resolver):
        """Profile references module, role references profile — both should be found."""
        results = resolver.find_referencing_manifests("profile_haproxy")
        contents = [p.read_text() for p in results]
        has_profile = any("profile::loadbalancer::haproxy" in c for c in contents)
        has_role = any("role::haproxy" in c for c in contents)
        assert has_profile
        assert has_role

    def test_no_references(self, resolver):
        results = resolver.find_referencing_manifests("nonexistent_module")
        assert results == []

    def test_excludes_self(self, resolver):
        """Module's own manifests should not be in the results."""
        results = resolver.find_referencing_manifests("profile_haproxy")
        for p in results:
            assert "profile_haproxy/manifests" not in str(p)


class TestInferClassName:
    @pytest.fixture()
    def resolver(self, control_repo):
        env_conf = control_repo / "environment.conf"
        modulepath = PuppetPathResolver.parse_modulepath(env_conf)
        return PuppetPathResolver(control_repo, modulepath)

    def test_init_pp(self, resolver, control_repo):
        pp = (
            control_repo
            / "site"
            / "modules"
            / "linux"
            / "profile_haproxy"
            / "manifests"
            / "init.pp"
        )
        assert resolver._infer_class_name(pp) == "profile_haproxy"

    def test_subclass(self, resolver, control_repo):
        pp = (
            control_repo
            / "site"
            / "modules"
            / "linux"
            / "profile_haproxy"
            / "manifests"
            / "config.pp"
        )
        assert resolver._infer_class_name(pp) == "profile_haproxy::config"

    def test_nested_class(self, resolver, control_repo):
        pp = (
            control_repo
            / "site"
            / "profile"
            / "manifests"
            / "loadbalancer"
            / "haproxy.pp"
        )
        assert resolver._infer_class_name(pp) == "profile::loadbalancer::haproxy"

    def test_role(self, resolver, control_repo):
        pp = control_repo / "site" / "role" / "manifests" / "haproxy.pp"
        assert resolver._infer_class_name(pp) == "role::haproxy"
