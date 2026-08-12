# Known false positives for `make check-deadcode` (vulture).
# These are names required by framework interfaces (Pydantic, Click,
# LangChain/LangGraph callbacks and middleware, context-manager `__exit__`),
# so they look "unused" to vulture even though the caller invokes them
# dynamically. Whitelisting matches by bare name across the whole codebase,
# not by location -- keep this list scoped to unambiguous framework hooks.

# Pydantic BaseSettings/BaseModel config attribute.
model_config

# Click CLI entry points (app.py) -- invoked by the Click framework, not
# called directly in code.
init
migrate
publish_project_cmd
publish_aap_cmd
adversarial_run

# contextlib/`__exit__` signature.
exc_type
exc_val
exc_tb

# LangGraph middleware/callback hook signature.
runtime

# LangChain BaseCallbackHandler overrides.
_.on_chat_model_start
_.on_llm_error
_.on_llm_end
_.on_tool_start
_.on_tool_end
_.on_tool_error

# langchain.agents.middleware.AgentMiddleware overrides.
_.before_agent
_.abefore_agent
_.after_agent
_.aafter_agent
_.before_model
_.abefore_model
