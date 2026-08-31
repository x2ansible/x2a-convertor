"""Tests for CheckReport construction from raw validator violation dicts."""

from apme_engine.graph.content_graph import (
    ContentGraph,
    ContentNode,
    NodeIdentity,
    NodeType,
)

from src.exporters.tools.apme import CheckReport


def _content_graph(nodes: dict[str, str]) -> ContentGraph:
    """Build a real ContentGraph with TASK nodes keyed by yaml_lines content.

    Args:
        nodes: Mapping of node_id (e.g. ``"tasks/security.yml:10"``) to the
            raw ``yaml_lines`` fragment ``filter_noqa_violations()`` inspects.

    Returns:
        A ContentGraph populated with one TASK node per entry.
    """
    graph = ContentGraph()
    for node_id, yaml_lines in nodes.items():
        identity = NodeIdentity(path=node_id, node_type=NodeType.TASK)
        graph.add_node(ContentNode(identity=identity, yaml_lines=yaml_lines))
    return graph


class TestCheckReportFromViolationDicts:
    """CheckReport.from_violation_dicts mirrors the gRPC daemon's post-fan-out steps."""

    def test_drops_violation_suppressed_by_inline_noqa(self):
        graph = _content_graph(
            {
                "tasks/security.yml:10": (
                    "- name: Disable SSH password authentication\n"
                    "  ansible.builtin.lineinfile: # noqa: L068\n"
                )
            }
        )
        violation_dicts = [
            {
                "rule_id": "L068",
                "severity": "info",
                "message": "Avoid lineinfile",
                "file": "tasks/security.yml",
                "line": 110,
                "path": "tasks/security.yml:10",
            }
        ]

        report = CheckReport.from_violation_dicts(violation_dicts, content_graph=graph)

        assert report.violations == []

    def test_keeps_violation_without_matching_noqa(self):
        graph = _content_graph(
            {
                "tasks/security.yml:9": (
                    "- name: Disable SSH root login\n  ansible.builtin.lineinfile:\n"
                )
            }
        )
        violation_dicts = [
            {
                "rule_id": "L068",
                "severity": "info",
                "message": "Avoid lineinfile",
                "file": "tasks/security.yml",
                "line": 100,
                "path": "tasks/security.yml:9",
            }
        ]

        report = CheckReport.from_violation_dicts(violation_dicts, content_graph=graph)

        assert len(report.violations) == 1
        assert report.violations[0].rule_id == "L068"
        assert report.violations[0].line == 100

    def test_deduplicates_identical_rule_file_line(self):
        violation_dicts = [
            {
                "rule_id": "R101",
                "severity": "medium",
                "message": "A parameterized command execution found",
                "file": "tasks/ssl.yml",
                "line": 30,
                "path": "tasks/ssl.yml:5",
                "source": "native",
            },
            {
                "rule_id": "R101",
                "severity": "medium",
                "message": "A parameterized command execution found",
                "file": "tasks/ssl.yml",
                "line": 30,
                "path": "tasks/ssl.yml:5",
                "source": "opa",
            },
        ]

        report = CheckReport.from_violation_dicts(violation_dicts, content_graph=None)

        assert len(report.violations) == 1

    def test_keeps_violations_when_content_graph_is_none(self):
        violation_dicts = [
            {
                "rule_id": "L017",
                "severity": "low",
                "message": "Avoid relative path in src",
                "file": "tasks/nginx.yml",
                "line": 40,
                "path": "tasks/nginx.yml:3",
            }
        ]

        report = CheckReport.from_violation_dicts(violation_dicts, content_graph=None)

        assert len(report.violations) == 1
