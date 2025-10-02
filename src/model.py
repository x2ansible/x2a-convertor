import os
import logging
import requests
from langchain.chat_models import init_chat_model

logger = logging.getLogger(__name__)


def list_models():
    """List all models available at the OPENAI_API_BASE endpoint, if set"""
    if os.getenv("OPENAI_API_BASE"):
        api_base = os.getenv("OPENAI_API_BASE")
        api_key = os.getenv("OPENAI_API_KEY", "not-needed")
        models_url = api_base.rstrip("/") + "/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        try:
            response = requests.get(models_url, headers=headers, timeout=10)
            response.raise_for_status()
            models = response.json().get("data", [])
            model_ids = [m.get("identifier") for m in models if "identifier" in m]
            logger.info(f"Available models at {api_base}: {model_ids}")
        except Exception as e:
            logger.warning(f"Could not list models from {models_url}: {e}")
    else:
        logger.warning("OPENAI_API_BASE is not set")


def get_model():
    """Initialize and return the configured language model"""
    model_name = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022")
    logger.info(f"Initializing model: {model_name}")
    logger.debug(f"OPENAI_API_BASE: {os.getenv('OPENAI_API_BASE')}")
    logger.debug(f"MAX_TOKENS: {os.getenv('MAX_TOKENS')}")
    logger.debug(f"TEMPERATURE: {os.getenv('TEMPERATURE')}")

    # Handle OpenAI-compatible local APIs
    if os.getenv("OPENAI_API_BASE"):
        return init_chat_model(
            model_name,
            base_url=os.getenv("OPENAI_API_BASE"),
            api_key=os.getenv("OPENAI_API_KEY", "not-needed"),
            model_provider=os.getenv("OPENAI_PROVIDER", "openai"),
            max_tokens=int(os.getenv("MAX_TOKENS", "8192")),
            temperature=float(os.getenv("TEMPERATURE", "0.1")),
        )

    return init_chat_model(model_name)
