# X2A Convertor

Infrastructure migration tool with AI-powered analysis and planning.

## Environment Variables

| Variable               | Description                                    | Example Values                                                                                           | Required                  |
| ---------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------- |
| `LLM_MODEL`            | Language model to use                          | `claude-3-5-sonnet-20241022`<br>`openai:gpt-4o`<br>`google_vertexai:gemini-2.5-pro`<br>`openai:qwen3:4b` | Yes                       |
| `OPENAI_API_BASE`      | Custom API endpoint for OpenAI-compatible APIs | `http://localhost:11434/v1`<br>`http://192.168.1.100:8000/v1`                                            | No                        |
| `OPENAI_API_KEY`       | API key for OpenAI or compatible services      | `sk-...` or `not-needed` for local                                                                       | No                        |
| `LOG_LEVEL`            | Logging verbosity                              | `INFO`, `DEBUG`, `ERROR`                                                                                 | No (default: INFO)        |
| `LANGCHAIN_DEBUG`      | Enable LangChain debug mode                    | `true`, `false`                                                                                          | No                        |
| `LANGCHAIN_TRACING_V2` | Enable LangChain tracing                       | `true`, `false`                                                                                          | No                        |
| `LANGCHAIN_API_KEY`    | LangSmith API key for tracing                  | `ls_...`                                                                                                 | No                        |
| `LANGCHAIN_PROJECT`    | LangSmith project name                         | `x2a-convertor`                                                                                          | No                        |
| `TARGET_REPO_PATH`     | Path to repository to analyze                  | `/path/to/chef-repo`<br>`../my-puppet-repo`                                                              | No (default: current dir) |
| `MAX_TOKENS`           | Maximum tokens for response                    | `8192`, `16384`, `32768`                                                                                 | No (default: 8192)        |
| `TEMPERATURE`          | Model temperature (0-1)                        | `0.1`, `0.5`, `1.0`                                                                                      | No (default: 0.1)         |

## Usage

Optionally, a `.env` file with following env variables can be created for development purposes.

### Enable debug logging
```bash
export LOG_LEVEL="DEBUG"
export LANGCHAIN_DEBUG="true"
```

### Local LLM example (Ollama)
```bash
# Local LLM example (Ollama)
export LLM_MODEL="openai:qwen3:4b"
#export LLM_MODEL="claude-3-5-sonnet-20241022"
export OPENAI_API_BASE="http://localhost:11434/v1"
export OPENAI_API_KEY="not-needed"
```

### Vertex AI running LLM in GCP
```bash
# to create ~/.config/gcloud/application_default_credentials.json:
gcloud auth application-default login

# to verify login:
gcloud auth list

# The value from https://console.cloud.google.com/home/dashboard
export VERTEXAI_PROJECT="myproject"

# to start the llama-stack service as a proxy to GCP
# (we plan to add more services here later)
podman-compose up

# in case of issues with starting the llama-stack service, mind clean-up based on
podman ps --all
```

More info: https://llama-stack.readthedocs.io/en/latest/providers/inference/remote_vertexai.html

## Run migration planning
```bash
uv run app.py init --source-dir ./input/hello_world "I want to migrate this Chef repository to Ansible"

# or

make name=hello_world run-init
```

## Development

```bash
# Format code
uv run ruff format

# Run application
uv run app.py
```
