"""Tests for deterministic Hiera configuration parser."""

import yaml

from src.inputs.puppet.hiera_parser import HieraConfigParser


class TestHieraConfigParserV5:
    """Test parsing of Hiera v5 configs."""

    def _create_module(self, tmp_path, hiera_config, data_files=None):
        """Create a puppet module with hiera config and optional data files."""
        module_path = tmp_path / "profile_test"
        module_path.mkdir()
        (module_path / "hiera.yaml").write_text(yaml.dump(hiera_config))

        if data_files:
            for rel_path, content in data_files.items():
                full_path = module_path / rel_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

        return module_path

    def test_parse_basic_v5(self, tmp_path):
        config = {
            "version": 5,
            "defaults": {"datadir": "data", "data_hash": "yaml_data"},
            "hierarchy": [
                {"name": "Common defaults", "path": "common.yaml"},
            ],
        }
        data_files = {"data/common.yaml": "---\npackage_name: haproxy\n"}
        module = self._create_module(tmp_path, config, data_files)

        parser = HieraConfigParser(str(module))
        hierarchy = parser.parse()

        assert hierarchy.version == 5
        assert len(hierarchy.levels) == 1
        assert hierarchy.levels[0].name == "Common defaults"
        assert hierarchy.total_data_files == 1
        assert len(hierarchy.levels[0].resolved_files) == 1

    def test_parse_multi_level_hierarchy(self, tmp_path):
        config = {
            "version": 5,
            "defaults": {"datadir": "data", "data_hash": "yaml_data"},
            "hierarchy": [
                {"name": "Per-node", "path": "nodes/%{trusted.certname}.yaml"},
                {"name": "OS family", "path": "os/%{facts.os.family}.yaml"},
                {"name": "Common", "path": "common.yaml"},
            ],
        }
        data_files = {
            "data/common.yaml": "---\nkey: value\n",
            "data/os/RedHat.yaml": "---\nfirewall: firewalld\n",
            "data/os/Debian.yaml": "---\nfirewall: ufw\n",
            "data/nodes/web01.yaml": "---\nport: 8080\n",
        }
        module = self._create_module(tmp_path, config, data_files)

        parser = HieraConfigParser(str(module))
        hierarchy = parser.parse()

        assert len(hierarchy.levels) == 3
        assert hierarchy.total_data_files == 4

        node_level = hierarchy.levels[0]
        assert node_level.name == "Per-node"
        assert len(node_level.resolved_files) == 1

        os_level = hierarchy.levels[1]
        assert os_level.name == "OS family"
        assert len(os_level.resolved_files) == 2

        common_level = hierarchy.levels[2]
        assert common_level.name == "Common"
        assert len(common_level.resolved_files) == 1

    def test_parse_paths_vs_path(self, tmp_path):
        """Test that 'paths' (plural) is handled correctly."""
        config = {
            "version": 5,
            "defaults": {"datadir": "data", "data_hash": "yaml_data"},
            "hierarchy": [
                {
                    "name": "Environment",
                    "paths": [
                        "environment/%{environment}.yaml",
                        "environment/default.yaml",
                    ],
                },
            ],
        }
        data_files = {
            "data/environment/production.yaml": "---\nmax: 16384\n",
            "data/environment/staging.yaml": "---\nmax: 4096\n",
            "data/environment/default.yaml": "---\nmax: 2048\n",
        }
        module = self._create_module(tmp_path, config, data_files)

        parser = HieraConfigParser(str(module))
        hierarchy = parser.parse()

        assert len(hierarchy.levels) == 2
        env_level = hierarchy.levels[0]
        assert env_level.name == "Environment"
        assert len(env_level.resolved_files) == 3  # all files match the glob pattern

        default_level = hierarchy.levels[1]
        assert default_level.name == "Environment"
        assert len(default_level.resolved_files) == 1

    def test_parse_custom_datadir(self, tmp_path):
        """Test per-hierarchy-entry datadir override."""
        config = {
            "version": 5,
            "defaults": {"datadir": "data"},
            "hierarchy": [
                {
                    "name": "Module data",
                    "datadir": "module_data",
                    "path": "common.yaml",
                },
            ],
        }
        data_files = {"module_data/common.yaml": "---\nkey: val\n"}
        module = self._create_module(tmp_path, config, data_files)

        parser = HieraConfigParser(str(module))
        hierarchy = parser.parse()

        assert hierarchy.levels[0].datadir == "module_data"
        assert len(hierarchy.levels[0].resolved_files) == 1

    def test_no_matching_data_files(self, tmp_path):
        config = {
            "version": 5,
            "hierarchy": [
                {"name": "Missing", "path": "nonexistent/%{something}.yaml"},
            ],
        }
        module = self._create_module(tmp_path, config)

        parser = HieraConfigParser(str(module))
        hierarchy = parser.parse()

        assert hierarchy.levels[0].resolved_files == []
        assert hierarchy.total_data_files == 0

    def test_caching(self, tmp_path):
        config = {"version": 5, "hierarchy": []}
        module = self._create_module(tmp_path, config)

        parser = HieraConfigParser(str(module))
        h1 = parser.parse()
        h2 = parser.parse()
        assert h1 is h2


class TestHieraConfigParserV3:
    """Test parsing of Hiera v3 configs (legacy)."""

    def _create_module(self, tmp_path, hiera_content, data_files=None):
        module_path = tmp_path / "profile_test"
        module_path.mkdir()
        (module_path / "hiera.yaml").write_text(hiera_content)

        if data_files:
            for rel_path, content in data_files.items():
                full_path = module_path / rel_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

        return module_path

    def test_parse_v3(self, tmp_path):
        hiera_content = yaml.dump(
            {
                ":backends:": ["yaml"],
                ":yaml:": {":datadir:": "data"},
                ":hierarchy:": ["common", "os/%{::osfamily}"],
            }
        )
        data_files = {
            "data/common.yaml": "---\nkey: val\n",
            "data/os/RedHat.yaml": "---\nfw: firewalld\n",
        }
        module = self._create_module(tmp_path, hiera_content, data_files)

        parser = HieraConfigParser(str(module))
        hierarchy = parser.parse()

        assert hierarchy.version == 3
        assert len(hierarchy.levels) == 2
        assert hierarchy.total_data_files == 2


class TestHieraConfigParserEdgeCases:
    """Test edge cases."""

    def test_no_hiera_config(self, tmp_path):
        module_path = tmp_path / "no_hiera"
        module_path.mkdir()

        parser = HieraConfigParser(str(module_path))
        hierarchy = parser.parse()

        assert hierarchy.levels == []
        assert hierarchy.total_data_files == 0

    def test_empty_hiera_config(self, tmp_path):
        module_path = tmp_path / "empty_hiera"
        module_path.mkdir()
        (module_path / "hiera.yaml").write_text("")

        parser = HieraConfigParser(str(module_path))
        hierarchy = parser.parse()

        assert hierarchy.levels == []

    def test_get_data_files_by_level(self, tmp_path):
        module_path = tmp_path / "profile_test"
        module_path.mkdir()
        config = {
            "version": 5,
            "defaults": {"datadir": "data"},
            "hierarchy": [
                {"name": "OS", "path": "os/%{facts.os.family}.yaml"},
                {"name": "Common", "path": "common.yaml"},
            ],
        }
        (module_path / "hiera.yaml").write_text(yaml.dump(config))
        (module_path / "data").mkdir()
        (module_path / "data" / "common.yaml").write_text("---\n")
        os_dir = module_path / "data" / "os"
        os_dir.mkdir()
        (os_dir / "RedHat.yaml").write_text("---\n")

        parser = HieraConfigParser(str(module_path))
        by_level = parser.get_data_files_by_level()

        assert "OS" in by_level
        assert "Common" in by_level
        assert len(by_level["OS"]) == 1
        assert len(by_level["Common"]) == 1

    def test_hiera_config_in_parent_dir(self, tmp_path):
        """Test finding hiera.yaml in parent directories."""
        (tmp_path / "hiera.yaml").write_text(
            yaml.dump(
                {
                    "version": 5,
                    "defaults": {"datadir": "data"},
                    "hierarchy": [{"name": "Common", "path": "common.yaml"}],
                }
            )
        )
        module_path = tmp_path / "modules" / "profile_test"
        module_path.mkdir(parents=True)

        parser = HieraConfigParser(str(module_path))
        hierarchy = parser.parse()

        assert hierarchy.version == 5
        assert len(hierarchy.levels) == 1
