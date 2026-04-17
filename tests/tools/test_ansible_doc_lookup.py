"""Tests for the AnsibleDocLookupTool and its internal helpers."""

from unittest.mock import Mock, patch

import pytest

from tools.ansible_doc_lookup import (
    AnsibleDocLookupTool,
    DocCLIBridge,
    _build_param_meta,
    _flatten_description,
    _strip_markup,
)

# ---------------------------------------------------------------------------
# Pure function tests (no ansible dependency)
# ---------------------------------------------------------------------------


class TestStripMarkup:
    """Tests for _strip_markup -- removes Ansible rst-ish C(), V(), etc."""

    def test_strips_c_markup(self) -> None:
        assert _strip_markup("Set to C(true) to enable") == "Set to true to enable"

    def test_strips_v_markup(self) -> None:
        assert _strip_markup("Use V(present) or V(absent)") == "Use present or absent"

    def test_strips_o_markup(self) -> None:
        assert _strip_markup("See O(state) option") == "See state option"

    def test_strips_i_markup(self) -> None:
        assert _strip_markup("The I(name) parameter") == "The name parameter"

    def test_strips_multiple_markup_types(self) -> None:
        text = "Set O(state) to V(present) using C(ansible)"
        assert _strip_markup(text) == "Set state to present using ansible"

    def test_leaves_plain_text_unchanged(self) -> None:
        assert _strip_markup("no markup here") == "no markup here"

    def test_handles_empty_string(self) -> None:
        assert _strip_markup("") == ""


class TestFlattenDescription:
    """Tests for _flatten_description -- joins list sentences, strips markup."""

    def test_joins_list_of_sentences(self) -> None:
        raw = ["First sentence.", "Second sentence."]
        assert _flatten_description(raw) == "First sentence. Second sentence."

    def test_handles_single_string(self) -> None:
        assert _flatten_description("Just one line.") == "Just one line."

    def test_strips_markup_in_list(self) -> None:
        raw = ["Set C(true) to enable.", "Defaults to V(false)."]
        assert _flatten_description(raw) == "Set true to enable. Defaults to false."

    def test_handles_empty_list(self) -> None:
        assert _flatten_description([]) == ""

    def test_handles_empty_string(self) -> None:
        assert _flatten_description("") == ""


class TestBuildParamMeta:
    """Tests for _build_param_meta -- builds inline metadata tags."""

    def test_required_param(self) -> None:
        opt = {"required": True, "type": "str"}
        assert _build_param_meta(opt) == ["required", "str"]

    def test_optional_with_default(self) -> None:
        opt = {"type": "bool", "default": False}
        assert _build_param_meta(opt) == ["bool", "default=False"]

    def test_with_choices(self) -> None:
        opt = {"type": "str", "choices": ["present", "absent"]}
        assert _build_param_meta(opt) == ["str", "choices=['present', 'absent']"]

    def test_all_metadata(self) -> None:
        opt = {
            "required": True,
            "type": "str",
            "default": "yes",
            "choices": ["yes", "no"],
        }
        assert _build_param_meta(opt) == [
            "required",
            "str",
            "default=yes",
            "choices=['yes', 'no']",
        ]

    def test_no_metadata(self) -> None:
        assert _build_param_meta({}) == []

    def test_none_default_is_skipped(self) -> None:
        opt = {"type": "str", "default": None}
        assert _build_param_meta(opt) == ["str"]


class TestDocCLIBridgeFormatModuleDocs:
    """Tests for DocCLIBridge.format_module_docs error handling."""

    def setup_method(self) -> None:
        with patch.object(DocCLIBridge, "__init__", lambda self: None):
            self.bridge = DocCLIBridge()

    def test_returns_formatted_docs_on_success(self) -> None:
        docs = {
            "doc": {
                "plugin_name": "test.module",
                "short_description": "Test",
                "options": {},
            }
        }
        with patch.object(self.bridge, "get_module_docs", return_value=docs):
            result = self.bridge.format_module_docs("test.module")

        assert result is not None
        assert "test.module -- Test" in result

    def test_returns_none_when_not_found(self) -> None:
        with patch.object(self.bridge, "get_module_docs", return_value=None):
            result = self.bridge.format_module_docs("fake.module")

        assert result is None

    def test_returns_error_string_on_exception(self) -> None:
        exc = Exception("module removed: Use replacement.module instead")
        with patch.object(self.bridge, "get_module_docs", side_effect=exc):
            result = self.bridge.format_module_docs("removed.module")

        assert result is not None
        assert "ERROR" in result
        assert "Use replacement.module instead" in result

    def test_surfaces_replacement_guidance_from_exception(self) -> None:
        exc = Exception("Missing documentation: Use microsoft.ad.membership instead.")
        with patch.object(self.bridge, "get_module_docs", side_effect=exc):
            result = self.bridge.format_module_docs(
                "ansible.windows.win_domain_membership"
            )

        assert result is not None
        assert "ERROR" in result
        assert "microsoft.ad.membership" in result


class TestFormatDoc:
    """Tests for DocCLIBridge._format_doc -- renders compact plaintext."""

    def test_basic_format(self) -> None:
        doc = {
            "plugin_name": "ansible.builtin.copy",
            "short_description": "Copy files to remote locations",
            "options": {
                "dest": {
                    "description": ["Remote absolute path."],
                    "type": "path",
                    "required": True,
                },
                "src": {
                    "description": ["Local path to a file."],
                    "type": "path",
                },
            },
        }
        result = DocCLIBridge._format_doc(doc)
        lines = result.split("\n")

        assert lines[0] == "ansible.builtin.copy -- Copy files to remote locations"
        assert lines[1] == ""
        assert lines[2] == "Parameters:"
        assert "  dest (required, path): Remote absolute path." in result
        assert "  src (path): Local path to a file." in result

    def test_parameters_are_sorted(self) -> None:
        doc = {
            "plugin_name": "test.module",
            "short_description": "Test",
            "options": {
                "zebra": {"description": "Z param.", "type": "str"},
                "alpha": {"description": "A param.", "type": "str"},
            },
        }
        result = DocCLIBridge._format_doc(doc)
        alpha_pos = result.index("alpha")
        zebra_pos = result.index("zebra")
        assert alpha_pos < zebra_pos

    def test_strips_markup_in_descriptions(self) -> None:
        doc = {
            "plugin_name": "test.module",
            "short_description": "A C(test) module",
            "options": {
                "state": {
                    "description": ["Set to V(present) or V(absent)."],
                    "type": "str",
                },
            },
        }
        result = DocCLIBridge._format_doc(doc)
        assert "test.module -- A test module" in result
        assert "Set to present or absent." in result

    def test_no_options(self) -> None:
        doc = {
            "plugin_name": "test.module",
            "short_description": "No params",
            "options": {},
        }
        result = DocCLIBridge._format_doc(doc)
        assert "Parameters:" in result
        assert result.count("\n") == 2

    def test_falls_back_to_module_key(self) -> None:
        doc = {
            "module": "fallback_name",
            "short_description": "Fallback",
            "options": {},
        }
        result = DocCLIBridge._format_doc(doc)
        assert result.startswith("fallback_name -- Fallback")

    def test_multisentence_description_preserved(self) -> None:
        doc = {
            "plugin_name": "test.module",
            "short_description": "Test",
            "options": {
                "port": {
                    "description": [
                        "The port to connect to.",
                        "Defaults to C(22) for SSH.",
                    ],
                    "type": "int",
                },
            },
        }
        result = DocCLIBridge._format_doc(doc)
        assert "The port to connect to. Defaults to 22 for SSH." in result


# ---------------------------------------------------------------------------
# Tool-level tests (mock the bridge to avoid ansible init)
# ---------------------------------------------------------------------------


_CANNED_MODULES = {
    "ansible.builtin.copy": "Copy files to remote locations",
    "ansible.builtin.file": "Manage files and file properties",
    "ansible.builtin.template": "Template a file out to a target host",
    "community.general.ufw": "Manage firewall with UFW",
}

_CANNED_FORMAT = (
    "ansible.builtin.copy -- Copy files\n\nParameters:\n"
    "  dest (required, path): Remote path."
)


class TestAnsibleDocLookupTool:
    """Tests for AnsibleDocLookupTool._run with a mocked bridge."""

    mock_format: Mock
    mock_list: Mock

    def setup_method(self) -> None:
        with patch.object(DocCLIBridge, "__init__", lambda self: None):
            self.tool = AnsibleDocLookupTool()
        bridge = self.tool._bridge
        self.mock_format = bridge.format_module_docs = Mock(return_value=_CANNED_FORMAT)
        self.mock_list = bridge.list_all_modules = Mock(
            return_value=dict(_CANNED_MODULES)
        )

    def test_module_lookup_returns_formatted_docs(self) -> None:
        result = self.tool._run(module_name="ansible.builtin.copy")

        self.mock_format.assert_called_once_with("ansible.builtin.copy")
        assert "ansible.builtin.copy -- Copy files" in result
        assert "dest (required, path)" in result

    def test_module_not_found_returns_error(self) -> None:
        self.mock_format.return_value = None

        result = self.tool._run(module_name="fake.nonexistent")

        assert "ERROR" in result
        assert "fake.nonexistent" in result

    def test_removed_module_returns_error_with_guidance(self) -> None:
        self.mock_format.return_value = (
            "ERROR: Module 'ansible.windows.win_domain_membership' "
            "documentation unavailable: module ansible.windows.win_domain_membership "
            "Missing documentation: Use microsoft.ad.membership instead."
        )

        result = self.tool._run(module_name="ansible.windows.win_domain_membership")

        assert "ERROR" in result
        assert "microsoft.ad.membership" in result

    def test_list_no_filter_returns_all(self) -> None:
        result = self.tool._run()

        assert "Available Ansible Modules (4)" in result
        assert "ansible.builtin.copy" in result
        assert "community.general.ufw" in result

    def test_list_with_filter_narrows_results(self) -> None:
        result = self.tool._run(list_filter="file")

        assert "Available Ansible Modules (1)" in result
        assert "ansible.builtin.file" in result
        assert "ansible.builtin.copy" not in result

    def test_list_filter_is_case_insensitive(self) -> None:
        result = self.tool._run(list_filter="UFW")

        assert "community.general.ufw" in result

    def test_list_filter_no_matches(self) -> None:
        result = self.tool._run(list_filter="zzz_nonexistent")

        assert "No modules found matching filter" in result

    def test_list_entries_are_sorted(self) -> None:
        result = self.tool._run()

        copy_pos = result.index("ansible.builtin.copy")
        file_pos = result.index("ansible.builtin.file")
        template_pos = result.index("ansible.builtin.template")
        ufw_pos = result.index("community.general.ufw")
        assert copy_pos < file_pos < template_pos < ufw_pos

    def test_module_name_takes_priority_over_list_filter(self) -> None:
        result = self.tool._run(module_name="ansible.builtin.copy", list_filter="file")

        self.mock_format.assert_called_once()
        self.mock_list.assert_not_called()
        assert "ansible.builtin.copy -- Copy files" in result


# ---------------------------------------------------------------------------
# Integration tests (real DocCLI bridge -- requires ansible installed)
# ---------------------------------------------------------------------------


class TestDocCLIBridgeIntegration:
    """Integration tests using real ansible DocCLI.

    These test actual module resolution across collection types.
    Skipped if ansible is not properly installed.
    """

    @pytest.fixture(autouse=True)
    def _bridge(self) -> None:
        self.bridge = DocCLIBridge()

    def test_builtin_module_docs(self) -> None:
        docs = self.bridge.get_module_docs("ansible.builtin.copy")
        assert docs is not None

        doc = docs["doc"]
        assert doc["plugin_name"] == "ansible.builtin.copy"
        assert "options" in doc
        assert "dest" in doc["options"]

    def test_builtin_format(self) -> None:
        result = self.bridge.format_module_docs("ansible.builtin.copy")

        assert result is not None
        assert result.startswith("ansible.builtin.copy --")
        assert "Parameters:" in result
        assert "dest (required" in result

    def test_community_module_docs(self) -> None:
        result = self.bridge.format_module_docs("community.general.ufw")

        assert result is not None
        assert "community.general.ufw --" in result
        assert "rule" in result

    def test_windows_module_docs(self) -> None:
        result = self.bridge.format_module_docs("ansible.windows.win_copy")

        assert result is not None
        assert "ansible.windows.win_copy --" in result
        assert "dest (required" in result

    def test_nonexistent_module_returns_none(self) -> None:
        result = self.bridge.format_module_docs("fake.collection.nonexistent")

        assert result is None

    def test_removed_module_returns_error_string(self) -> None:
        """Modules removed from collections should return an error, not raise."""
        result = self.bridge.format_module_docs("ansible.windows.win_domain_membership")

        # Should not raise; returns either None or an error string
        if result is not None:
            assert "ERROR" in result

    def test_list_all_modules_returns_dict(self) -> None:
        modules = self.bridge.list_all_modules()

        assert isinstance(modules, dict)
        assert len(modules) > 100
        assert "ansible.builtin.copy" in modules

    def test_list_collection_modules(self) -> None:
        modules = self.bridge.list_collection_modules("ansible.builtin")

        assert isinstance(modules, dict)
        assert len(modules) > 10
        assert all(fqcn.startswith("ansible.builtin.") for fqcn in modules)

    def test_context_restored_after_list(self) -> None:
        """Verify that CLIARGS is restored after listing."""
        self.bridge.list_all_modules()
        result = self.bridge.format_module_docs("ansible.builtin.copy")

        assert result is not None
        assert "ansible.builtin.copy --" in result

    def test_embedded_defaults_in_description(self) -> None:
        """Modules that put defaults in description text should preserve them."""
        result = self.bridge.format_module_docs("community.windows.win_firewall_rule")

        assert result is not None
        assert "domain,private,public" in result
