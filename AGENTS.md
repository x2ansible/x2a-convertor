# Agents.md

This file provides guidance to any software agent (Claude Code, Codex) working with code in this repository.

## Project Overview

X2A Convertor is an AI-powered infrastructure migration tool that converts Chef, Puppet, PowerShell, and Salt configurations to Ansible. It uses LangGraph with LLM-powered agents for analysis and migration.

The system has two major pipelines:

- **Input pipeline** (`src/inputs/`): Technology-specific analyzers that parse source infrastructure code (Chef, Puppet, PowerShell, Salt) and produce a structured migration plan
- **Export pipeline** (`src/exporters/`): Technology-agnostic agents that consume migration plans and produce Ansible roles

## Development Commands

```bash
# Install dependencies
uv sync

# Format + lint
uv run ruff format
uv run ruff check . --fix

# Type checking
uv run pyrefly check

# Run tests (excludes evals)
uv run pytest -m "not eval"

# Run evals only
uv run pytest -m "eval"

# Full CI check
make ci-check

# Run migration workflow
make name=hello_world run-init      # Step 1: init
make name=hello_world run-analyze   # Step 2: analyze
make name=hello_world run-migrate   # Step 3: migrate
```

## Architecture

### Agent Hierarchy

All agents inherit from `BaseAgent[S: BaseState]` (`src/base_agent.py`), which provides:

- Automatic telemetry via `__call__` -> `execute()`
- Three invocation modes: `invoke_react()`, `invoke_structured()`, `invoke_llm()`
- Declarative tool configuration via `BASE_TOOLS` class variable
- State-derived tools via `extra_tools_from_state()` hook
- Middleware stack (rules injection, goal validation, conversation compaction, debug dump)

Two intermediate base classes specialize `BaseAgent`:

| Base Class | File | Purpose |
|---|---|---|
| `InputAgent[S]` | `src/inputs/input_agent.py` | Sets `RULES_FILE = INPUT_AGENTS_FILE` for all analysis agents |
| `ExportAgent[S]` | `src/exporters/export_agent.py` | Sets `RULES_FILE = EXPORT_AGENTS_FILE` for all export agents |

### Input Pipeline (Analysis)

Each technology has a `*Subagent` orchestrator that wires analysis services into a LangGraph `StateGraph`. Services are `InputAgent` subclasses that call `invoke_structured()` with a Pydantic schema to extract structured data from source files.

Pattern (using Puppet as example):

```
PuppetSubagent (orchestrator, not a BaseAgent)
  -> ManifestAnalysisService(InputAgent)    # invoke_structured(ManifestExecutionAnalysis)
  -> HieraDataAnalysisService(InputAgent)   # invoke_structured(HieraDataAnalysis)
  -> TemplateAnalysisService(InputAgent)    # invoke_structured(PuppetTemplateAnalysis)
  -> ReportWriterAgent(InputAgent)          # invoke_react() with tools
  -> AnalysisValidationAgent(InputAgent)    # invoke_react() with tools
  -> CleanupAgent(InputAgent)              # invoke_react()
```

### Export Pipeline (Migration)

`ToAnsibleSubagent` orchestrates the export workflow:

```
ToAnsibleSubagent (orchestrator)
  -> AAPDiscoveryAgent     # Discover AAP Private Hub collections
  -> CredentialAgent       # Extract credentials for AAP
  -> PlanningAgent         # Build migration checklist (invoke_react)
  -> WriteAgent            # Write all Ansible files (invoke_react, internal retry loop)
  -> MoleculeAgent         # Generate Molecule test scaffolding
  -> ReviewAgent           # Review generated code
  -> ValidationAgent       # Lint + fix validation issues
```

### State Management

States are `@dataclass` classes inheriting from `BaseState` (`src/types/base_state.py`). They use an immutable update pattern:

```python
@dataclass
class BaseState(ABC):
    user_message: str
    path: str
    telemetry: Telemetry | None = field(default=None, kw_only=True)
    failed: bool = field(default=False, kw_only=True)
    failure_reason: str = field(default="", kw_only=True)

    def update(self, **kwargs) -> "BaseState":
        return replace(self, **kwargs)

    def mark_failed(self, reason: str) -> "BaseState":
        return self.update(failed=True, failure_reason=reason)
```

Key concrete states:
- `InitState` (`src/init/init_state.py`) -- init workflow
- `ExportState` (`src/exporters/state.py`) -- export workflow
- `FileAnalysisState` (`src/types/file_analysis_state.py`) -- per-file analysis
- `PuppetState`, `ChefState`, etc. -- technology-specific analysis

### Workflow Pattern (LangGraph)

All multi-agent workflows follow the same pattern:

```python
class SomeSubagent:
    def __init__(self):
        self.agent_a = AgentA(model=self.model)
        self.agent_b = AgentB(model=self.model)
        self._workflow = self._create_workflow()

    def _create_workflow(self):
        workflow = StateGraph(SomeState)
        workflow.add_node("step_a", self.agent_a)
        workflow.add_node("step_b", self.agent_b)
        workflow.add_edge(START, "step_a")
        workflow.add_conditional_edges("step_a", self._check_failure_after_agent)
        workflow.add_edge("step_b", END)
        return workflow.compile()

    def _check_failure_after_agent(self, state) -> Literal["step_b", "finalize"]:
        if state.failed:
            return "finalize"
        return "step_b"
```

Agents are callable (`__call__` on `BaseAgent`) and used directly as graph nodes.

## Prompt System

### File Organization

Prompts live in `prompts/` as either Markdown (`.md`) or Jinja2 (`.j2`) files. Loaded via `get_prompt()` from `prompts/get_prompt.py`:

```python
from prompts.get_prompt import get_prompt

# Returns JinjaTemplate for .j2, raw string for .md
prompt = get_prompt("puppet_manifest_analysis_system")
rendered = prompt.format(document=document.to_document())
```

### Naming Convention

Prompts follow a strict naming pattern: `{pipeline}_{phase}_{role}.{md|j2}`

- **pipeline**: `init_`, `chef_`, `puppet_`, `powershell_`, `ansible_`, `export_`
- **phase**: what the agent does (e.g., `manifest_analysis`, `ansible_write`, `planning`)
- **role**: `system` or `task`

Every agent has a **system** prompt (persona + rules) and a **task** prompt (specific work with template variables). Examples:

```
puppet_manifest_analysis_system.j2   # System: "You are a Puppet analysis expert..."
puppet_manifest_analysis_task.j2     # Task: "Analyze this manifest: {{ document }}"
export_ansible_write_system.j2       # System: conversion rules, tool docs
export_ansible_write_task.j2         # Task: module context, checklist, plans
```

### Writing Prompts

When writing or modifying prompts:

1. **Use Jinja2 (`.j2`)** for prompts that need template variables. Markdown (`.md`) is not recommended anymore
2. **Never hardcode** file content, paths, module names, or technology-specific details in prompts -- pass them as template variables
3. **Use `DocumentFile.to_document()`** to embed file content in prompts instead of raw text with code fences:
   ```python
   from src.types.document import DocumentFile

   doc = DocumentFile.from_path(file_path)
   prompt.format(document=doc.to_document())
   # Produces: <document><source>path</source><document_content>...</document_content></document>
   ```
4. **System prompts** define the agent's role, available tools, rules and boundaries. They should be technology-aware but not module-specific
5. **Task prompts** provide the specific context: which module, which files, what checklist state. They receive all dynamic data via Jinja2 variables
6. **Conditional includes** for technology-specific sections:
   ```jinja2
   {% if source_technology == 'Puppet' %}
   {% include 'write_from_puppet.md' %}
   {% endif %}
   ```

## Structured Output

For extracting structured data from LLM responses, use `invoke_structured()` with a Pydantic `BaseModel` schema:

```python
from pydantic import BaseModel

class ManifestAnalysis(BaseModel):
    class_name: str | None = None
    resources: list[ResourceInfo] = []
    dependencies: list[str] = []

# In agent.execute():
result = self.invoke_structured(ManifestAnalysis, messages, metrics)
```

`invoke_structured()` handles:
- Automatic retry on validation failure (up to `max_retries`, default 3)
- Schema instruction injection (tells the LLM to use structured output)
- Token metric recording
- Returns `None` if all retries fail

Structured output models live in technology-specific `models.py` files:
- `src/inputs/puppet/models.py`
- `src/inputs/chef/models.py`
- `src/inputs/ansible/models.py`
- `src/types/metadata.py`, `src/types/credential.py`, `src/types/rules.py`

## Tools

Custom tools extend `X2ATool` (`tools/base_tool.py`), which provides structured logging bound to the agent that invokes the tool:

```python
from tools.base_tool import X2ATool

class MyTool(X2ATool):
    name: str = "my_tool"
    description: str = "Does something"
    args_schema: type[BaseModel] = MyToolInput

    def _run(self, **kwargs) -> str:
        self.log.info("Running tool")  # Logs with agent= and tool= bindings
        ...
```

Tools are declared on agents as factory callables in `BASE_TOOLS`:

```python
class WriteAgent(ExportAgent[ExportState]):
    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: ReadFileTool(),
        lambda: AnsibleWriteTool(),
        lambda: AnsibleLintTool(),
    ]
```

For state-dependent tools (like checklist operations), override `extra_tools_from_state()`.

## Configuration

Settings use Pydantic `BaseSettings` with environment variable binding (`src/config/settings.py`):

```python
from src.config import get_settings

settings = get_settings()
model_name = settings.llm.model
max_tokens = settings.llm.max_tokens
```

Key environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `LLM_MODEL` | LLM model identifier | `openai/gpt-oss-120b-maas` |
| `MAX_TOKENS` | Max tokens per response | `8192` |
| `TEMPERATURE` | Model temperature | `0.1` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `JSON_LINES` | Path for agent message dumps | None |
| `MAX_WRITE_ATTEMPTS` | Max file writing retries | `10` |
| `MAX_VALIDATION_ATTEMPTS` | Max validation retries | `5` |

## Middleware

Agents use a middleware stack configured in `BaseAgent.middleware()`:

| Middleware | Purpose |
|---|---|
| `GoalValidationMiddleware` | Validates agent achieved its `GOAL`; retries if not |
| `RulesMiddleware` | Injects rules from `RULES_FILE` as a message at startup |
| `X2ASummarizationMiddleware` | Compacts conversation when token count exceeds threshold |
| `AgentDumpMiddleware` | Dumps messages to JSON Lines for debugging (when `JSON_LINES` is set) |

## Python Standards

- Python 3.13+ required
- Use modern type hints: `str | None`, `list[str]`, `dict[str, int]`, `BaseAgent[S: BaseState]`
- Never use `Optional`, `Union`, `List`, `Dict`, `Tuple` from `typing` -- use built-in generics and `|` syntax
- All code must be class-based (see class hierarchy above)
- Keep functions under 40 lines
- Skip else clauses -- use early returns and guard clauses
- Use functional programming for filtering/mapping: list comprehensions, `filter()`, `map()`
- When passing file content to LLM prompts, use `DocumentFile` from `src/types/document.py` and its `to_document()` XML format
- Never use emojis

## Testing

```bash
uv run pytest -m "not eval"   # Unit/integration tests
uv run pytest -m "eval"       # LLM evaluation tests
```

Tests are organized under `tests/` mirroring the `src/` structure. Evals are marked with `@pytest.mark.eval` and test actual LLM output quality.

## File Organization

- `input/` or `examples/` -- Source repositories to analyze
- `prompts/` -- All LLM prompt templates (system + task pairs)
- `src/init/` -- Init workflow (migration plan generation)
- `src/inputs/` -- Technology-specific analyzers (Chef, Puppet, PowerShell, Salt, Ansible)
- `src/exporters/` -- Export pipeline (technology-agnostic Ansible generation)
- `src/types/` -- Core data structures (states, metadata, telemetry, documents)
- `src/middleware/` -- Agent middleware (rules, summarization, goal validation)
- `src/config/` -- Settings management
- `tools/` -- Custom LangChain tools
- `tests/` -- Test suite (mirrors src/ structure)
