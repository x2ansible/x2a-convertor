# Agents.md

This file provides guidance to any software agent (Claude-code, openai-codex) when working with code in this repository.

## Project Overview

X2A Convertor is an AI-powered infrastructure migration tool that converts Chef, Puppet, and Salt configurations to Ansible. It uses LangGraph with various LLM providers for analysis and migration planning.

## Development Commands

### Setup and Installation
```bash
# Install dependencies
uv sync

# Clean environment 
uv venv --clear
rm -rf ./tmp
```

### Code Quality and Formatting
```bash
# Format code
uv run ruff format

# Check and fix linting issues
uv run ruff check . --fix

# CI checks (for GitHub Actions)
uv run ruff check . --output-format=github
uv run ruff format --check
```

### Running the Application
```bash
# Main CLI interface
uv run app.py

# Initialize migration project
uv run app.py init --source-dir ./input/hello_world "I want to migrate this Chef repository to Ansible"

# Using Makefile shortcut
make name=hello_world run-init

# Analyze project (detailed module analysis)
uv run app.py analyze "migration requirements" --source-dir ./path/to/source

# Migrate specific module
uv run app.py migrate "module-name"

# Validate migrated module
uv run app.py validate "module-name"
```

## Architecture Overview

### Core Modules
- `app.py`: Main CLI entry point using Click framework
- `src/init.py`: Project initialization and high-level analysis
- `src/inputs/`: Technology-specific analyzers (Chef, Puppet, Salt)
  - `analyze.py`: Root analyzer that detects technology and delegates
  - `chef.py`: Chef cookbook analyzer with LangChain agents
  - `puppet.py`: Puppet manifest analyzer
  - `salt.py`: Salt state analyzer
- `src/exporters/`: Output generators (currently Ansible)
- `src/migrate.py`: Migration orchestrator
- `src/validate.py`: Migration validation
- `src/model.py`: LLM model configuration and setup
- `prompts/`: LangGraph prompt templates for different analysis phases

### AI Integration
- Uses LangGraph with configurable LLM providers (Claude, OpenAI, Vertex AI, local models)
- Prompt-driven analysis stored in `prompts/` directory
- LangGraph for complex multi-step workflows
- Configurable via environment variables in `.env`

### Key Environment Variables
- `LLM_MODEL`: Model selection (e.g., "claude-3-5-sonnet-20241022", "openai:gpt-4o")
- `OPENAI_API_BASE`: Custom endpoints for local/compatible APIs
- `TARGET_REPO_PATH`: Repository path to analyze
- `LOG_LEVEL`: Debug/logging configuration
- `LANGCHAIN_DEBUG`: Enable LangChain debugging

### Workflow Pattern
1. **Init**: High-level analysis for project planning (`MIGRATION-PLAN.md`)
2. **Analyze**: Detailed module analysis with dependency mapping
3. **Migrate**: Generate Ansible playbooks for specific modules
4. **Validate**: Compare original vs generated configurations

### File Organization
- Input repositories placed in `input/` directory
- Generated migration plans as markdown files in project root
- Ansible output in `ansible/` directory structure
- All operations are stateless and Git-based

## Development Notes

- Python 3.13+ required (specified in pyproject.toml)
- Uses uv for dependency management
- Ruff for code formatting and linting
- No persistent state - all data derived from Git repositories
- Modular architecture supports adding new input/output formats
- Never use emojis
- Keep code complexity small and avoid using else clauses
