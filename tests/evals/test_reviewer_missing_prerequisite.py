"""Evaluation tests for the Ansible ReviewAgent false negative in FLPATH-4862.

Regression coverage for the reviewer missing a generated task that changes a
file (or manages a service) whose owning application the role never puts on the
target -- e.g. editing /etc/ssh/sshd_config without installing openssh-server
and without guarding for the file's existence.

Category 2 of the reviewer prompt names NO concrete file/app examples, so every
case here is a TRANSFER test: passing means the reviewer applied the general
"enumerate every changed file -> verify its owning app exists -> install/guard"
procedure, not that it pattern-matched a named example.

Each case builds a role that reproduces the defect in a different shape, runs
the reviewer with its REAL system/task prompts and REAL tool set, and asserts
the reviewer catches it -- either by naming it in the report or by applying a
guard/package fix directly.

These are eval tests: they require a live LLM and are non-deterministic.
"""

import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from langchain.agents import create_agent
from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_core.messages import HumanMessage

from prompts.get_prompt import get_prompt
from src.model import get_model
from tools.ansible_write import AnsibleWriteTool
from tools.validated_write import ValidatedWriteTool


def _has_valid_api_config() -> bool:
    """Check if any supported LLM provider is configured."""
    if os.getenv("OPENAI_API_BASE") and os.getenv("OPENAI_API_KEY"):
        return True
    if os.getenv("ANTHROPIC_API_KEY"):
        return True
    if os.getenv("GEMINI_API_KEY"):
        return True
    model = os.getenv("LLM_MODEL", "")
    if model.startswith("vertex_ai/") and os.getenv("VERTEXAI_PROJECT"):
        return True
    if model.startswith("bedrock/") and (
        os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        or os.getenv("AWS_ACCESS_KEY_ID")
        or os.getenv("AWS_PROFILE")
    ):
        return True
    return False


pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not _has_valid_api_config(),
        reason="No LLM provider configured (OPENAI_API_BASE+OPENAI_API_KEY, "
        "ANTHROPIC_API_KEY, GEMINI_API_KEY, or vertex_ai LLM_MODEL+VERTEXAI_PROJECT)",
    ),
]

# Generic "the reviewer treated this as a prerequisite/existence problem"
# vocabulary. Combined with a case's own target tokens so a keyword raised for an
# unrelated finding does not count as a catch for this file.
CONCEPT_KW = (
    "not installed",
    "never install",
    "isn't installed",
    "is not installed",
    "no package",
    "missing package",
    "package dependency",
    "prerequisite",
    "may not exist",
    "might not exist",
    "may be absent",
    "does not exist",
    "file exists",
    "existence",
    "guard",
    "create: false",
    "stat",
    "install the",
    "install openssh",
    "install redis",
    "install logrotate",
)


@dataclass
class Case:
    """One reproduction of the Category 2 defect in a distinct shape."""

    id: str
    tasks_main: str
    # substrings that identify THIS defect's file/app in the reviewer's report
    target_tokens: tuple[str, ...]
    # substrings that, if present in tasks/main.yml AFTER review, mean a fix was
    # applied (guard added, or the owning package installed). None of these appear
    # in the original tasks_main, so their presence is a real change.
    fix_markers: tuple[str, ...]
    # extra files the role needs (relative path under the role -> content)
    extra_files: dict[str, str] = field(default_factory=dict)
    defaults: str = "---\n"
    # source technology label passed to the reviewer's task prompt (a label only;
    # the reviewer prompt has no per-technology branching)
    source_technology: str = "Chef"


CASES: list[Case] = [
    # A) The exact FLPATH-4862 defect: nginx role that also hardens sshd by
    # editing /etc/ssh/sshd_config -- base OS daemon the role does not own, so
    # the correct remedy is a stat/when guard (not installing openssh).
    Case(
        id="sshd_config_edit_no_openssh",
        tasks_main="""---
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present

- name: Deploy nginx configuration
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
    mode: "0644"
    backup: true

- name: Disable root login if configured
  ansible.builtin.lineinfile:
    path: /etc/ssh/sshd_config
    regexp: "^#?PermitRootLogin.*$"
    line: "PermitRootLogin no"
""",
        target_tokens=("sshd_config", "/etc/ssh", "openssh"),
        fix_markers=("create: false", ".stat", "ansible.builtin.stat", "openssh"),
        extra_files={"templates/nginx.conf.j2": "worker_processes auto;\n"},
        defaults="---\nnginx_worker_processes: auto\n",
    ),
    # B) Puppet profile_redis_cluster shape: the role configures redis.conf and
    # manages the redis service but never installs redis (upstream relies on an
    # external module). Role owns the app, so the correct remedy is to install it.
    Case(
        id="redis_conf_and_service_no_install",
        source_technology="Puppet",
        tasks_main="""---
- name: Deploy redis configuration
  ansible.builtin.template:
    src: redis.conf.j2
    dest: /etc/redis/redis.conf
    mode: "0640"

- name: Ensure redis is running
  ansible.builtin.service:
    name: redis
    state: started
    enabled: true
""",
        target_tokens=("redis",),
        fix_markers=(
            "ansible.builtin.package",
            "ansible.builtin.dnf",
            "ansible.builtin.apt",
            "ansible.builtin.yum",
            "create: false",
            "ansible.builtin.stat",
        ),
        extra_files={
            "templates/redis.conf.j2": "maxmemory {{ redis_maxmemory | default('256mb') }}\n"
        },
    ),
    # C) Puppet haproxy/app_stack shape: the role installs its own app but drops a
    # config file into /etc/logrotate.d/, a directory owned by a DIFFERENT package
    # (logrotate) that is never installed. Tests that the reviewer identifies the
    # owner of the file being written, not just the app being configured.
    Case(
        id="logrotate_dropin_no_logrotate_install",
        source_technology="Puppet",
        tasks_main="""---
- name: Install myapp
  ansible.builtin.package:
    name: myapp
    state: present

- name: Configure log rotation for myapp
  ansible.builtin.copy:
    dest: /etc/logrotate.d/myapp
    content: |
      /var/log/myapp/*.log {
        daily
        rotate 7
      }
    mode: "0644"
""",
        target_tokens=("logrotate",),
        fix_markers=(
            "name: logrotate",
            "- logrotate",
            "create: false",
            "ansible.builtin.stat",
        ),
    ),
    # D) Puppet puppetlabs-inifile shape: an ini_setting -> community.general.ini_file
    # edit of a service config whose package the role never installs. ini_file's
    # `create` defaults to true, so an ungated edit silently writes a bogus my.cnf on
    # a host that has no mysql-server. Role owns the app -> correct remedy is install.
    Case(
        id="ini_file_mysql_no_install",
        source_technology="Puppet",
        tasks_main="""---
- name: Tune MySQL max connections
  community.general.ini_file:
    path: /etc/my.cnf
    section: mysqld
    option: max_connections
    value: "500"
    mode: "0644"
""",
        target_tokens=("my.cnf", "mysql"),
        fix_markers=(
            "ansible.builtin.package",
            "ansible.builtin.dnf",
            "ansible.builtin.apt",
            "ansible.builtin.yum",
            "create: false",
            "create: no",
            "ansible.builtin.stat",
        ),
    ),
    # E) Puppet file-resource shape with a METADATA-ONLY change: a
    # `file { ...: mode => ... }` (no content) -> ansible.builtin.file that only
    # tightens permissions on a config whose package the role never installs. Tests
    # the prompt's "ANY change counts, even mode/owner/group" clause -- file with
    # state=file errors on a host where the file is absent.
    Case(
        id="file_mode_only_haproxy_no_install",
        source_technology="Puppet",
        tasks_main="""---
- name: Restrict permissions on HAProxy config
  ansible.builtin.file:
    path: /etc/haproxy/haproxy.cfg
    mode: "0640"
    state: file
""",
        target_tokens=("haproxy",),
        fix_markers=(
            "ansible.builtin.package",
            "ansible.builtin.dnf",
            "ansible.builtin.apt",
            "ansible.builtin.yum",
            "create: false",
            "ansible.builtin.stat",
        ),
    ),
]


def _build_role(root: Path, case: Case) -> Path:
    role = root / "roles" / case.id
    (role / "tasks").mkdir(parents=True)
    (role / "defaults").mkdir(parents=True)
    (role / "tasks" / "main.yml").write_text(case.tasks_main)
    (role / "defaults" / "main.yml").write_text(case.defaults)
    for rel, content in case.extra_files.items():
        path = role / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return role


def _prerequisite_caught(case: Case, report: str, tasks_after: str) -> bool:
    """True if the reviewer surfaced OR fixed the missing-owner prerequisite."""
    report_l = report.lower()
    tasks_l = tasks_after.lower()
    # (a) Named as a finding: references this file/app AND a prerequisite concept.
    named = any(t in report_l for t in case.target_tokens) and any(
        kw in report_l for kw in CONCEPT_KW
    )
    # (b) Fixed in place: a guard or an install of the owning package was added.
    fixed = any(m.lower() in tasks_l for m in case.fix_markers)
    return named or fixed


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_reviewer_flags_missing_prerequisite(case: Case):
    """The reviewer must not report 'no issues' for a change whose owning app
    the role never puts on the target."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        role = _build_role(root, case)
        tasks_file = role / "tasks" / "main.yml"

        system_message = get_prompt("export_ansible_review_system").format()
        user_prompt = get_prompt("export_ansible_review_task").format(
            module=case.id,
            ansible_path=str(role),
            source_path=str(root / "src"),
            source_technology=case.source_technology,
            checklist="",
        )

        agent = create_agent(
            model=get_model(),
            tools=[
                ListDirectoryTool(),
                ReadFileTool(),
                FileSearchTool(),
                ValidatedWriteTool(),
                AnsibleWriteTool(),
            ],
            system_prompt=system_message,
        )

        result = agent.invoke(
            {"messages": [HumanMessage(content=user_prompt)]},
            {"recursion_limit": 50},
        )

        report = "\n".join(
            str(getattr(m, "content", "")) for m in result["messages"]
        )
        tasks_after = tasks_file.read_text()

        assert _prerequisite_caught(case, report, tasks_after), (
            f"Reviewer false negative for case '{case.id}': it neither reported "
            "nor fixed the missing owning-application prerequisite.\n\n"
            f"--- tasks/main.yml after review ---\n{tasks_after}\n"
            f"--- report tail ---\n{report[-1500:]}"
        )


# ---------------------------------------------------------------------------
# Robustness test: several defects at once, buried among correct tasks and
# unrelated distractor findings, repeated N times to measure a hit-rate rather
# than a single pass/fail. This stresses the enumerate-then-check discipline:
# the reviewer must find EVERY planted defect, not just the obvious one, and do
# so repeatably despite the model's non-determinism.
# ---------------------------------------------------------------------------


@dataclass
class Defect:
    """One planted missing-owner defect inside the multi-defect role."""

    name: str
    # substrings identifying this defect's file/app in a report finding line
    target_tokens: tuple[str, ...]
    # package-name-SPECIFIC markers that only appear if THIS defect was fixed in
    # tasks/main.yml (no cross-talk with other defects' fixes or pre-existing
    # package tasks in the role)
    install_markers: tuple[str, ...]


# A realistic-sized web-app role that installs its OWN stack correctly, but hides
# three precondition defects among the correct tasks plus a couple of unrelated
# real issues (an ungated command, a service before its config) as distractors.
MULTI_DEFECT_TASKS = """---
- name: Install acme web server
  ansible.builtin.package:
    name: acme-web
    state: present

- name: Create acme group
  ansible.builtin.group:
    name: acme

- name: Create acme user
  ansible.builtin.user:
    name: acme
    group: acme
    system: true

- name: Create acme config directory
  ansible.builtin.file:
    path: /etc/acme
    state: directory
    owner: acme
    group: acme
    mode: "0755"

- name: Deploy acme configuration
  ansible.builtin.copy:
    dest: /etc/acme/acme.conf
    content: "listen = 0.0.0.0:8080\\n"
    owner: acme
    group: acme
    mode: "0644"

- name: Disable root SSH login
  ansible.builtin.lineinfile:
    path: /etc/ssh/sshd_config
    regexp: "^#?PermitRootLogin.*$"
    line: "PermitRootLogin no"

- name: Create web root
  ansible.builtin.file:
    path: /var/www/acme
    state: directory
    owner: acme
    group: acme
    mode: "0755"

- name: Deploy landing page
  ansible.builtin.copy:
    dest: /var/www/acme/index.html
    content: "<h1>acme</h1>\\n"
    mode: "0644"

- name: Tune database connections
  community.general.ini_file:
    path: /etc/my.cnf
    section: mysqld
    option: max_connections
    value: "500"
    mode: "0644"

- name: Configure acme log rotation
  ansible.builtin.copy:
    dest: /etc/logrotate.d/acme
    content: |
      /var/log/acme/*.log {
        daily
        rotate 7
      }
    mode: "0644"

- name: Start acme service
  ansible.builtin.service:
    name: acme-web
    state: started
    enabled: true

- name: Run acme database migrations
  ansible.builtin.command: acme-web db upgrade
"""

MULTI_CASE = Case(
    id="multi_buried_defects",
    source_technology="Puppet",
    tasks_main=MULTI_DEFECT_TASKS,
    target_tokens=(),  # unused; per-defect checking is used instead
    fix_markers=(),  # unused
)

MULTI_DEFECTS: list[Defect] = [
    # sshd_config edited, openssh never installed (remedy: guard)
    Defect(
        name="sshd_config/openssh",
        target_tokens=("sshd_config", "/etc/ssh", "openssh"),
        install_markers=("openssh",),
    ),
    # /etc/my.cnf edited, mysql-server never installed (remedy: install)
    Defect(
        name="my.cnf/mysql",
        target_tokens=("my.cnf", "mysql"),
        install_markers=("mysql-server", "name: mysql", "mariadb"),
    ),
    # /etc/logrotate.d drop-in, logrotate never installed (remedy: install owner)
    Defect(
        name="logrotate.d/logrotate",
        target_tokens=("logrotate",),
        install_markers=("name: logrotate", "- logrotate"),
    ),
]


def _named_in_report(
    report: str, target_tokens: tuple[str, ...], window: int = 3
) -> bool:
    """True if some short span of the report mentions this defect's file/app AND
    a prerequisite/existence concept together (scoped so a concept keyword raised
    for a DIFFERENT defect does not falsely count for this one)."""
    lines = report.lower().splitlines()
    for i in range(len(lines)):
        block = " ".join(lines[i : i + window])
        if any(t in block for t in target_tokens) and any(
            k in block for k in CONCEPT_KW
        ):
            return True
    return False


def _defect_caught(defect: Defect, report: str, tasks_after: str) -> bool:
    tasks_l = tasks_after.lower()
    return _named_in_report(report, defect.target_tokens) or any(
        m.lower() in tasks_l for m in defect.install_markers
    )


def _run_reviewer(role: Path) -> tuple[str, str]:
    """Run the real reviewer agent over a role; return (report, tasks/main.yml)."""
    system_message = get_prompt("export_ansible_review_system").format()
    user_prompt = get_prompt("export_ansible_review_task").format(
        module=MULTI_CASE.id,
        ansible_path=str(role),
        source_path=str(role.parent.parent / "src"),
        source_technology=MULTI_CASE.source_technology,
        checklist="",
    )
    agent = create_agent(
        model=get_model(),
        tools=[
            ListDirectoryTool(),
            ReadFileTool(),
            FileSearchTool(),
            ValidatedWriteTool(),
            AnsibleWriteTool(),
        ],
        system_prompt=system_message,
    )
    result = agent.invoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        {"recursion_limit": 50},
    )
    report = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    tasks_after = (role / "tasks" / "main.yml").read_text()
    return report, tasks_after


def test_reviewer_catches_multiple_buried_defects():
    """Over REPEAT runs, the reviewer must catch EACH of the 3 buried defects in
    at least PASS_THRESHOLD runs. Measures robustness under non-determinism."""
    repeat = int(os.getenv("REPEAT", "10"))
    threshold = int(os.getenv("PASS_THRESHOLD", str(math.ceil(repeat * 0.8))))

    hits = {d.name: 0 for d in MULTI_DEFECTS}
    all_caught_runs = 0
    per_run: list[str] = []

    for i in range(repeat):
        with tempfile.TemporaryDirectory() as tmp:
            role = _build_role(Path(tmp), MULTI_CASE)
            report, tasks_after = _run_reviewer(role)
            caught = {
                d.name for d in MULTI_DEFECTS if _defect_caught(d, report, tasks_after)
            }
            for name in caught:
                hits[name] += 1
            if len(caught) == len(MULTI_DEFECTS):
                all_caught_runs += 1
            per_run.append(f"  run {i + 1}: {sorted(caught)}")

    per_defect = "\n".join(f"  {n}: {h}/{repeat}" for n, h in hits.items())
    summary = (
        f"\nMulti-defect reviewer hit-rate over {repeat} runs "
        f"(threshold {threshold}/{repeat} per defect):\n{per_defect}\n"
        f"all-3-caught: {all_caught_runs}/{repeat}\n" + "\n".join(per_run)
    )
    print(summary)

    below = {n: h for n, h in hits.items() if h < threshold}
    assert not below, f"Defects below threshold {threshold}/{repeat}: {below}\n{summary}"
