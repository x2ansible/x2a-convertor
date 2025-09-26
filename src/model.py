import os
from langchain.chat_models import init_chat_model


def get_model():
    """Initialize and return the configured language model"""
    model_name = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022")

    # Handle OpenAI-compatible local APIs
    if os.getenv("OPENAI_API_BASE"):
        return init_chat_model(
            model_name,
            base_url=os.getenv("OPENAI_API_BASE"),
            api_key=os.getenv("OPENAI_API_KEY", "not-needed"),
            max_tokens=int(os.getenv("MAX_TOKENS", "8192")),
            temperature=float(os.getenv("TEMPERATURE", "0.1")),
        )

    return init_chat_model(model_name)
